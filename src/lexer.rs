//! Lexer module for Gàidheal.

pub mod tokenizer;

pub use tokenizer::{tokenize, LexError, Spanned, Token, Tokenizer};
