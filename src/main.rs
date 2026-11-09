//! Gàidheal CLI entry point.
//! Reads a `.gaidheal` file, parses, interprets, and prints.

use clap::Parser as ClapParser;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

use gaidheal::interpreter::Interpreter;
use gaidheal::lexer::tokenize;
use gaidheal::parser::Parser;

#[derive(ClapParser, Debug)]
#[command(name = "gaidheal", version, about = "Gàidheal esolang interpreter")]
struct Args {
    /// Input file (must have .gaidheal extension)
    #[arg(value_name = "FILE")]
    file: PathBuf,

    /// Show the token stream
    #[arg(long)]
    tokens: bool,

    /// Show the parsed AST
    #[arg(long)]
    ast: bool,

    /// Stack depth limit
    #[arg(long, default_value_t = 1000)]
    stack_depth: usize,
}

fn main() {
    let args = Args::parse();

    if args.file.extension().and_then(|s| s.to_str()) != Some("gaidheal") {
        eprintln!("error: file must have .gaidheal extension");
        std::process::exit(1);
    }

    let source = fs::read_to_string(&args.file).unwrap_or_else(|e| {
        eprintln!("error reading {}: {}", args.file.display(), e);
        std::process::exit(1);
    });

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

    let program = match Parser::new(&source) {
        Ok(mut p) => match p.parse() {
            Ok(p) => p,
            Err(e) => {
                eprintln!("parse error: {}", e);
                std::process::exit(1);
            }
        },
        Err(e) => {
            eprintln!("lex error: {}", e);
            std::process::exit(1);
        }
    };

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

fn print_ast(block: &gaidheal::parser::Block, indent: usize) {
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
