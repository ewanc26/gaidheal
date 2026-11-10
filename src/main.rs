//! Gàidheal CLI entry point.
//! Reads a `.gaidheal` file, then either interprets it, emits C
//! (`--emit-c`), or compiles and runs a native binary (`-o`, `--run`).
//! With no file, starts the interactive REPL.

use clap::Parser as ClapParser;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

use gaidheal::codegen::{emit_c, runtime_header_path};
use gaidheal::interpreter::Interpreter;
use gaidheal::lexer::tokenize;
use gaidheal::parser::{Block, Parser};

#[derive(ClapParser, Debug)]
#[command(name = "gaidheal", version, about = "Gàidheal esolang interpreter and C compiler")]
struct Args {
    /// Input file (must have .gaidheal extension); omit to start the REPL
    #[arg(value_name = "FILE")]
    file: Option<PathBuf>,

    /// Emit generated C instead of running (writes to stdout or -o)
    #[arg(long, requires = "file")]
    emit_c: bool,

    /// Output path: C source with --emit-c, native binary otherwise
    #[arg(short, long, value_name = "PATH")]
    output: Option<PathBuf>,

    /// Compile a native binary and run it immediately
    #[arg(long, requires = "file")]
    run: bool,

    /// C compiler used to build native binaries [default: $GAIDHEAL_CC or cc]
    #[arg(long, value_name = "CC")]
    cc: Option<String>,

    /// Show the token stream
    #[arg(long, requires = "file")]
    tokens: bool,

    /// Show the parsed AST
    #[arg(long, requires = "file")]
    ast: bool,

    /// Stack depth limit
    #[arg(long, default_value_t = 1000)]
    stack_depth: usize,
}

fn main() {
    let args = Args::parse();

    // No file: interactive REPL, sharing stdin between program input and faigh reads.
    let Some(file) = args.file else {
        if let Err(e) = gaidheal::repl::run_repl(io::stdin(), io::stdout(), args.stack_depth) {
            eprintln!("runtime error: {}", e);
            std::process::exit(1);
        }
        return;
    };

    if file.extension().and_then(|s| s.to_str()) != Some("gaidheal") {
        eprintln!("error: file must have .gaidheal extension");
        std::process::exit(1);
    }

    let source = fs::read_to_string(&file).unwrap_or_else(|e| {
        eprintln!("error reading {}: {}", file.display(), e);
        std::process::exit(1);
    });

    let program = Parser::new(&source)
        .and_then(|mut p| p.parse())
        .unwrap_or_else(|e| {
            eprintln!("parse error: {}", e);
            std::process::exit(1);
        });

    let source_name = file
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("program.gaidheal")
        .to_string();

    if args.emit_c {
        let c = emit_c(&program, &source_name, args.stack_depth, runtime_header_path());
        match &args.output {
            Some(path) => {
                if let Err(e) = fs::write(path, &c) {
                    eprintln!("error writing {}: {}", path.display(), e);
                    std::process::exit(1);
                }
            }
            None => {
                print!("{}", c);
                let _ = io::stdout().flush();
            }
        }
        return;
    }

    // Compile a native binary (and optionally run it).
    if args.output.is_some() || args.run {
        compile_and_run(
            &program,
            &source_name,
            args.stack_depth,
            args.output.as_deref(),
            args.run,
            args.cc.as_deref(),
        );
        return;
    }

    if args.tokens {
        match tokenize(&source) {
            Ok(tokens) => {
                println!("// tokens:");
                for t in tokens {
                    println!("  {:?}", t.token);
                }
            }
            Err(e) => {
                eprintln!("lex error: {}", e);
                std::process::exit(1);
            }
        }
    }

    if args.ast {
        println!("// ast:");
        print_ast(&program, 0);
    }

    // Only build the interpreter when the program will actually run.
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut interp = Interpreter::with_depth(stdin.lock(), stdout.lock(), args.stack_depth);
    if let Err(e) = interp.run(&program) {
        let _ = io::stdout().flush();
        eprintln!("runtime error: {}", e);
        std::process::exit(1);
    }
    let _ = io::stdout().flush();
}

/// Emit C for the program, build it with the system C compiler, and
/// optionally run the resulting binary with inherited stdio.
fn compile_and_run(
    program: &Block,
    source_name: &str,
    depth: usize,
    output: Option<&Path>,
    run: bool,
    cc_arg: Option<&str>,
) {
    let cc = cc_arg
        .map(|s| s.to_string())
        .or_else(|| std::env::var("GAIDHEAL_CC").ok())
        .unwrap_or_else(|| "cc".to_string());
    let c = emit_c(program, source_name, depth, runtime_header_path());

    // With -o hello.c keep the C next to the binary; with -o hello write
    // hello.c alongside; with --run alone use a temporary directory.
    let binary_path = match output {
        Some(path) if path.extension().and_then(|s| s.to_str()) == Some("c") => {
            write_or_exit(path, &c);
            path.with_extension("")
        }
        Some(path) => {
            let c_path = path.with_extension("c");
            write_or_exit(&c_path, &c);
            path.to_path_buf()
        }
        None => {
            let base = std::env::temp_dir().join(source_name.replace('.', "_"));
            let c_path = base.with_extension("c");
            write_or_exit(&c_path, &c);
            base
        }
    };

    let status = Command::new(&cc)
        .arg("-std=c99")
        .arg("-O2")
        .arg(binary_path.with_extension("c").as_os_str())
        .arg("-lm")
        .arg("-o")
        .arg(binary_path.as_os_str())
        .status();
    match status {
        Ok(s) if s.success() => {}
        Ok(s) => {
            eprintln!("error: {} exited with {}", cc, s);
            std::process::exit(1);
        }
        Err(e) => {
            eprintln!("error: could not run {}: {}", cc, e);
            std::process::exit(1);
        }
    }

    if !run {
        println!("wrote {}", binary_path.display());
        return;
    }

    match Command::new(binary_path.as_os_str()).status() {
        Ok(s) => std::process::exit(s.code().unwrap_or(1)),
        Err(e) => {
            eprintln!("error: could not run {}: {}", binary_path.display(), e);
            std::process::exit(1);
        }
    }
}

fn write_or_exit(path: &Path, c: &str) {
    if let Err(e) = fs::write(path, c) {
        eprintln!("error writing {}: {}", path.display(), e);
        std::process::exit(1);
    }
}

fn print_ast(block: &Block, indent: usize) {
    use gaidheal::parser::Op;
    let pad = "  ".repeat(indent);
    for op in block {
        match op {
            Op::If(stmt) => {
                println!("{}{} {{", pad, if matches!(stmt.form, gaidheal::parser::IfForm::Ma) { "ma" } else { "mha" });
                print_ast(&stmt.then_branch, indent + 1);
                if let Some(else_branch) = &stmt.else_branch {
                    println!("{}}} no {{", pad);
                    print_ast(else_branch, indent + 1);
                }
                println!("{}}}", pad);
            }
            Op::Loop(stmt) => {
                println!("{}cuairt ({:?}) {{", pad, stmt.kind);
                print_ast(&stmt.body, indent + 1);
                println!("{}}}", pad);
            }
            other => println!("{}{:?}", pad, other),
        }
    }
}
