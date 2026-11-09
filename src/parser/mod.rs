//! Parser module for Gàidheal.

pub mod parser;

pub use parser::{
    format_number, parse_program, Block, IfForm, IfStmt, LoopKind, LoopStmt, Op, ParseError,
    Parser,
};
