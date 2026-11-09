//! Interactive REPL for Gàidheal.
//!
//! Reads program text line by line, executes complete blocks against a
//! persistent interpreter, and shows the stack after every evaluation.
//! Unfinished source (an open block, a `cuir` waiting for its number, an
//! open comment) is buffered until it completes; parse errors after
//! complete input reset the buffer and return to the prompt.
//!
//! Program input read by `faigh`/`fhaigh` comes from the same stream as
//! the REPL lines, so typed lines can double as program input.

use crate::interpreter::{InterpError, Interpreter};
use crate::parser::{ParseError, Parser};
use std::io::{Read, Write};

const PROMPT: &str = "gaidheal> ";
const CONTINUATION_PROMPT: &str = "    ...> ";

/// Run the REPL over the given streams. Returns when the input ends.
pub fn run_repl<R: Read, W: Write>(input: R, out: W, depth: usize) -> Result<(), InterpError> {
    let mut interp = Interpreter::with_depth(input, out, depth);
    let mut buffer = String::new();

    interp.write_out("Gàidheal REPL — every block ends with `criòch`. EOF exits.\n")?;

    loop {
        let prompt = if buffer.is_empty() { PROMPT } else { CONTINUATION_PROMPT };
        interp.write_out(prompt)?;
        interp.flush_out()?;

        let line = match interp.read_line()? {
            None => break,
            Some(line) => line,
        };
        buffer.push_str(&line);
        buffer.push('\n');

        if buffer.trim().is_empty() {
            buffer.clear();
            continue;
        }

        match Parser::new(&buffer) {
            Ok(mut parser) => match parser.parse() {
                Ok(program) => {
                    if let Err(e) = interp.run(&program) {
                        interp.write_out(format!("runtime error: {}\n", e).as_str())?;
                    }
                    print_stack(&mut interp)?;
                    buffer.clear();
                }
                Err(e) if e.incomplete => { /* keep buffering */ }
                Err(e) => {
                    report_error(&mut interp, &e)?;
                    buffer.clear();
                }
            },
            Err(e) if e.incomplete => { /* open comment; keep buffering */ }
            Err(e) => {
                report_error(&mut interp, &e)?;
                buffer.clear();
            }
        }
    }

    interp.flush_out()
}

fn report_error<R: Read, W: Write>(interp: &mut Interpreter<R, W>, e: &ParseError) -> Result<(), InterpError> {
    interp.write_out(format!("parse error: {}\n", e).as_str())
}

fn print_stack<R: Read, W: Write>(interp: &mut Interpreter<R, W>) -> Result<(), InterpError> {
    if interp.stack().is_empty() {
        return Ok(());
    }
    let rendered: Vec<String> = interp
        .stack()
        .iter()
        .map(|v| crate::parser::format_number(*v))
        .collect();
    interp.write_out(
        format!("stac({}): {}\n", rendered.len(), rendered.join(" ")).as_str(),
    )
}
