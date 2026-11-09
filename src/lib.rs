//! Gàidheal: an esoteric stack-based programming language written in
//! Scottish Gaelic.
//!
//! All values are 64-bit doubles on a single operand stack (default depth
//! 1000). Each root word has three forms selected by initial-consonant
//! mutation: base (destructive/primary), lenited (variant element), and
//! eclipsed (non-destructive/structural).

pub mod builtins;
pub mod interpreter;
pub mod lexer;
pub mod parser;

#[cfg(feature = "cli")]
pub mod repl;

pub use interpreter::{InterpError, Interpreter};
pub use parser::{parse_program, Block, Op};

/// Run a program from source against byte streams. Returns the program
/// output. Useful for tests and embedding.
pub fn run_source<R: std::io::Read, W: std::io::Write>(
    src: &str,
    input: R,
    out: W,
) -> Result<(), Box<dyn std::error::Error>> {
    let program = parse_program(src)?;
    let mut interp = Interpreter::new(input, out);
    interp.run(&program)?;
    Ok(())
}
