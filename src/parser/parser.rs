//! Parser for Gàidheal.
//!
//! Turns the flat token stream into a block tree. Every block ends with
//! `criòch`. An `ma`/`mha` block may be followed by a `no` (else) block,
//! which shares the closing `criòch`:
//!
//! ```text
//! ma
//!     <then-branch>
//! no
//!     <else-branch>
//! criòch
//! ```

use crate::builtins::{self, Word};
use crate::lexer::{tokenize, Spanned, Token};
use std::fmt;

/// A program is a sequence of operations.
pub type Block = Vec<Op>;

/// A single parsed operation.
#[derive(Debug, Clone, PartialEq)]
pub enum Op {
    Push(f64),
    Copy(usize),
    Roll(usize),
    Dup,
    Over,
    StackDepth,
    Swap,
    Reverse,
    Tuck,
    Drop,
    Nip,
    Clear,
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Pow,
    Lt,
    Gt,
    Eq,
    PrintNum,
    PrintChar,
    ReadNum,
    ReadChar,
    EofFlag,
    Break,
    Continue,
    If(IfStmt),
    Loop(LoopStmt),
}

/// An `ma`/`mha` conditional, with an optional `no` (else) branch.
#[derive(Debug, Clone, PartialEq)]
pub struct IfStmt {
    pub form: IfForm,
    pub then_branch: Block,
    pub else_branch: Option<Block>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IfForm {
    /// `ma` — run the block if the popped condition is nonzero.
    Ma,
    /// `mha` — run the block if the popped condition is zero.
    Mha,
}

/// A `cuairt`/`chuairt`/`gcuairt` loop.
#[derive(Debug, Clone, PartialEq)]
pub struct LoopStmt {
    pub kind: LoopKind,
    pub body: Block,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LoopKind {
    /// `cuairt` — while: pops a condition BEFORE each iteration.
    While,
    /// `chuairt` — do-while: pops a condition AFTER the body.
    DoWhile,
    /// `gcuairt` — infinite loop, exited with `cùl`.
    Infinite,
}

/// A parse failure, with the offending line number. `incomplete` marks
/// recoverable end-of-input states — an open block, a `cuir` waiting for
/// its number, an open comment — that a REPL can extend instead of
/// rejecting.
#[derive(Debug, Clone, PartialEq)]
pub struct ParseError {
    pub message: String,
    pub line: usize,
    pub incomplete: bool,
    /// True when the failure comes from the tokenizer rather than the
    /// grammar, so tools can print `lex error:` vs `parse error:`.
    pub lexical: bool,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for ParseError {}

impl From<crate::lexer::LexError> for ParseError {
    fn from(e: crate::lexer::LexError) -> Self {
        ParseError {
            message: e.message,
            line: e.line,
            incomplete: e.incomplete,
            lexical: true,
        }
    }
}

pub struct Parser {
    tokens: Vec<Spanned>,
    pos: usize,
}

/// Parse a source string into a program block.
pub fn parse_program(src: &str) -> Result<Block, ParseError> {
    Parser::new(src)?.parse()
}

impl Parser {
    pub fn new(src: &str) -> Result<Self, ParseError> {
        Ok(Parser { tokens: tokenize(src)?, pos: 0 })
    }

    /// Clone the token at the cursor without consuming it.
    fn peek(&self) -> Option<Spanned> {
        self.tokens.get(self.pos).cloned()
    }

    /// Consume and return the token at the cursor.
    fn next(&mut self) -> Option<Spanned> {
        let t = self.tokens.get(self.pos).cloned();
        if t.is_some() {
            self.pos += 1;
        }
        t
    }

    fn err<T>(&self, message: impl Into<String>, line: usize) -> Result<T, ParseError> {
        Err(ParseError { message: message.into(), line, incomplete: false, lexical: false })
    }

    /// Like [`Parser::err`], but marks the error as recoverable at end of
    /// input: the user may simply not have finished typing yet.
    fn err_incomplete<T>(&self, message: impl Into<String>, line: usize) -> Result<T, ParseError> {
        Err(ParseError { message: message.into(), line, incomplete: true, lexical: false })
    }

    /// Parse the whole program. The top level ends at end-of-file, so
    /// any `criòch` seen here is a stray closer.
    pub fn parse(&mut self) -> Result<Block, ParseError> {
        let (block, _) = self.parse_seq(&[], false)?;
        Ok(block)
    }

    /// Parse ops until one of `enders` (which is consumed) or, when
    /// `enders` is empty, end of file. Returns the block and the word that
    /// closed it ("eof" at the top level).
    fn parse_seq(&mut self, enders: &[&str], in_loop: bool) -> Result<(Block, String), ParseError> {
        let mut ops: Block = Vec::new();

        loop {
            let spanned = match self.peek() {
                Some(s) => s,
                None => {
                    return self.err_incomplete("unexpected end of file", self.line_of_last());
                }
            };
            let line = spanned.line;

            match spanned.token {
                Token::Eof => {
                    if enders.is_empty() {
                        return Ok((ops, "eof".to_string()));
                    }
                    return self.err_incomplete(
                        format!("missing `{}` before end of file", enders[0]),
                        line,
                    );
                }
                Token::Number(n) => {
                    return self.err(
                        format!(
                            "a number may only appear immediately after `cuir`/`chuir`/`gcuir`; found `{}`",
                            format_number(n)
                        ),
                        line,
                    );
                }
                Token::Word(w) => {
                    if enders.contains(&w.as_str()) {
                        self.next();
                        return Ok((ops, w));
                    }
                    match builtins::lookup(&w) {
                        Some(Word::If) => {
                            self.next();
                            ops.push(Op::If(self.parse_if(IfForm::Ma, in_loop)?));
                        }
                        Some(Word::IfZero) => {
                            self.next();
                            ops.push(Op::If(self.parse_if(IfForm::Mha, in_loop)?));
                        }
                        Some(Word::Else) => {
                            return self.err(
                                "`no` (else) may only follow an `ma`/`mha` block, before its `criòch`",
                                line,
                            );
                        }
                        Some(Word::While) => {
                            self.next();
                            ops.push(Op::Loop(self.parse_loop(LoopKind::While)?));
                        }
                        Some(Word::DoWhile) => {
                            self.next();
                            ops.push(Op::Loop(self.parse_loop(LoopKind::DoWhile)?));
                        }
                        Some(Word::Infinite) => {
                            self.next();
                            ops.push(Op::Loop(self.parse_loop(LoopKind::Infinite)?));
                        }
                        Some(Word::Break) => {
                            if !in_loop {
                                return self.err(format!("`{}` may only appear inside a loop body", w), line);
                            }
                            self.next();
                            ops.push(Op::Break);
                        }
                        Some(Word::Continue) => {
                            if !in_loop {
                                return self.err(format!("`{}` may only appear inside a loop body", w), line);
                            }
                            self.next();
                            ops.push(Op::Continue);
                        }
                        Some(Word::Push) => {
                            self.next();
                            ops.push(Op::Push(self.expect_number("cuir")?));
                        }
                        Some(Word::Copy) => {
                            self.next();
                            ops.push(Op::Copy(self.expect_index("chuir")?));
                        }
                        Some(Word::Roll) => {
                            self.next();
                            ops.push(Op::Roll(self.expect_index("gcuir")?));
                        }
                        Some(word) => {
                            self.next();
                            ops.push(simple_op(word));
                        }
                        None => {
                            if w == "criòch" {
                                return self.err("`criòch` closes a block, but no block is open here", line);
                            }
                            return self.err(format!("unknown word `{}`", w), line);
                        }
                    }
                }
            }
        }
    }

    /// `ma B [no E] criòch` (the same shape for `mha`). The then-branch is
    /// closed by either `no` or the block's `criòch`; `ma`/`mha` pop their
    /// condition at runtime.
    fn parse_if(&mut self, form: IfForm, in_loop: bool) -> Result<IfStmt, ParseError> {
        let (then_branch, ender) = self.parse_seq(&["no", "criòch"], in_loop)?;
        let else_branch = if ender == "no" {
            Some(self.parse_seq(&["criòch"], in_loop)?.0)
        } else {
            None
        };
        Ok(IfStmt { form, then_branch, else_branch })
    }

    /// `cuairt B criòch` and friends.
    fn parse_loop(&mut self, kind: LoopKind) -> Result<LoopStmt, ParseError> {
        let (body, _) = self.parse_seq(&["criòch"], true)?;
        Ok(LoopStmt { kind, body })
    }

    /// Expect a number literal for `cuir`.
    fn expect_number(&mut self, word: &str) -> Result<f64, ParseError> {
        match self.next() {
            Some(Spanned { token: Token::Number(n), .. }) => Ok(n),
            Some(Spanned { token: Token::Word(w), line }) => {
                self.err(format!("expected a number after `{}`, found `{}`", word, w), line)
            }
            Some(Spanned { token: Token::Eof, line }) => {
                self.err_incomplete(format!("expected a number after `{}`, found end of file", word), line)
            }
            None => self.err_incomplete(
                format!("expected a number after `{}`, found end of file", word),
                self.line_of_last(),
            ),
        }
    }

    /// Expect a whole, non-negative index for `chuir`/`gcuir`.
    fn expect_index(&mut self, word: &str) -> Result<usize, ParseError> {
        match self.next() {
            Some(Spanned { token: Token::Number(n), line }) => {
                if n < 0.0 || n.fract() != 0.0 {
                    return self.err(
                        format!("`{}` needs a whole, non-negative index, found `{}`", word, format_number(n)),
                        line,
                    );
                }
                Ok(n as usize)
            }
            Some(Spanned { token: Token::Word(w), line }) => {
                self.err(format!("expected a stack index after `{}`, found `{}`", word, w), line)
            }
            Some(Spanned { token: Token::Eof, line }) => {
                self.err_incomplete(format!("expected a stack index after `{}`, found end of file", word), line)
            }
            None => self.err_incomplete(
                format!("expected a stack index after `{}`, found end of file", word),
                self.line_of_last(),
            ),
        }
    }

    fn line_of_last(&self) -> usize {
        self.tokens.last().map(|s| s.line).unwrap_or(1)
    }
}

fn simple_op(word: Word) -> Op {
    use Word::*;
    match word {
        Push | Copy | Roll | If | IfZero | Else | While | DoWhile | Infinite | Break | Continue => {
            unreachable!("handled by the parser")
        }
        Dup => Op::Dup,
        Over => Op::Over,
        Depth => Op::StackDepth,
        Swap => Op::Swap,
        Reverse => Op::Reverse,
        Tuck => Op::Tuck,
        Drop => Op::Drop,
        Nip => Op::Nip,
        Clear => Op::Clear,
        Add => Op::Add,
        Sub => Op::Sub,
        Mul => Op::Mul,
        Div => Op::Div,
        Rem => Op::Rem,
        Pow => Op::Pow,
        Lt => Op::Lt,
        Gt => Op::Gt,
        Eq => Op::Eq,
        PrintNum => Op::PrintNum,
        PrintChar => Op::PrintChar,
        ReadNum => Op::ReadNum,
        ReadChar => Op::ReadChar,
        EofFlag => Op::EofFlag,
    }
}

/// Render a number the way the interpreter prints values.
pub fn format_number(v: f64) -> String {
    v.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_words_to_ops() {
        let block = parse_program("cuir 1 tog abair").unwrap();
        assert_eq!(block, vec![Op::Push(1.0), Op::Dup, Op::PrintNum]);
    }

    #[test]
    fn parses_if_with_and_without_else() {
        let block = parse_program("ma cuir 1 criòch mha cuir 2 no cuir 3 criòch").unwrap();
        assert_eq!(block.len(), 2);
        assert_eq!(
            block[0],
            Op::If(IfStmt {
                form: IfForm::Ma,
                then_branch: vec![Op::Push(1.0)],
                else_branch: None,
            })
        );
        assert_eq!(
            block[1],
            Op::If(IfStmt {
                form: IfForm::Mha,
                then_branch: vec![Op::Push(2.0)],
                else_branch: Some(vec![Op::Push(3.0)]),
            })
        );
    }

    #[test]
    fn parses_loops_and_control() {
        let block = parse_program("cuairt cuìl criòch chuairt chuìl criòch gcuairt cùl criòch").unwrap();
        assert_eq!(block.len(), 3);
        for (i, kind) in [LoopKind::While, LoopKind::DoWhile, LoopKind::Infinite].iter().enumerate() {
            match &block[i] {
                Op::Loop(stmt) => {
                    assert_eq!(stmt.kind, *kind);
                    // the While body breaks with `cuìl`, accepted as a `cùl` alias
                    assert_eq!(stmt.body, vec![if *kind == LoopKind::DoWhile { Op::Continue } else { Op::Break }]);
                }
                other => panic!("expected loop, found {:?}", other),
            }
        }
    }

    #[test]
    fn numbers_only_after_cuir_family() {
        assert!(parse_program("cuir 5").is_ok());
        assert!(parse_program("toc 5").is_err());
        assert!(parse_program("5").is_err());
    }

    #[test]
    fn indices_must_be_whole_and_non_negative() {
        assert!(parse_program("chuir 0").is_ok());
        assert!(parse_program("gcuir 2").is_ok());
        assert!(parse_program("chuir -1").is_err());
        assert!(parse_program("gcuir 1.5").is_err());
    }

    #[test]
    fn unterminated_block_is_an_error() {
        assert!(parse_program("ma cuir 1").is_err());
        assert!(parse_program("gcuairt cuir 1").is_err());
    }

    #[test]
    fn break_outside_loop_is_an_error() {
        assert!(parse_program("cùl").is_err());
        assert!(parse_program("chuìl").is_err());
        assert!(parse_program("ma cùl criòch").is_err());
    }

    #[test]
    fn else_shares_the_closing_word() {
        // The else branch must be closed by the SAME criòch, so this parses.
        let block = parse_program("ma no cuir 9 criòch").unwrap();
        match &block[0] {
            Op::If(stmt) => {
                assert!(stmt.then_branch.is_empty());
                assert_eq!(stmt.else_branch.as_deref(), Some(&[Op::Push(9.0)][..]));
            }
            other => panic!("expected if, found {:?}", other),
        }
        // But a bare `no` at the top level is an error.
        assert!(parse_program("no criòch").is_err());
    }

    #[test]
    fn break_inside_if_inside_loop_parses() {
        assert!(parse_program("gcuairt ma cuìl criòch cuìl criòch").is_ok());
    }

    #[test]
    fn incomplete_programs_are_marked() {
        // Open blocks and a `cuir` waiting for its number are marked
        // incomplete so a REPL can wait for more input.
        for src in [
            "ma",
            "ma cuir 1",
            "gcuairt cuir 1",
            "ma cuir 1 no",
            "cuir",
            "chuir",
            "( comment",
        ] {
            let err = parse_program(src).unwrap_err();
            assert!(err.incomplete, "`{}` should be incomplete: {:?}", src, err);
        }
        // Real errors are complete.
        for src in ["toc", "5", "cùl", "cuir 1 2", ")", "@", "cuir 1 )"] {
            let err = parse_program(src).unwrap_err();
            assert!(!err.incomplete, "`{}` should be complete: {:?}", src, err);
        }
    }
}
