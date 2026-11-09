//! Interpreter for Gàidheal.
//!
//! A stack machine over the parser's block tree. All values are 64-bit
//! doubles on a single operand stack (default depth 1000). Input and
//! output are abstracted over [`Read`] / [`Write`] so tests can drive
//! programs with in-memory streams.

use crate::parser::{Block, IfForm, LoopKind, LoopStmt, Op};

use std::fmt;
use std::io::{BufRead, Read, Write};

/// A runtime failure.
#[derive(Debug)]
pub enum InterpError {
    StackUnderflow,
    StackOverflow { limit: usize },
    InvalidIndex { index: usize, depth: usize },
    DivisionByZero,
    InvalidCodePoint(f64),
    NumberRead(String),
    InvalidUtf8,
    Io(std::io::Error),
}

impl fmt::Display for InterpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            InterpError::StackUnderflow => {
                write!(f, "stack underflow: an operation popped more values than the stack had")
            }
            InterpError::StackOverflow { limit } => {
                write!(f, "stack overflow: the depth limit of {} was reached", limit)
            }
            InterpError::InvalidIndex { index, depth } => {
                write!(f, "stack index {} is out of range (depth {})", index, depth)
            }
            InterpError::DivisionByZero => write!(f, "division by zero"),
            InterpError::InvalidCodePoint(v) => {
                write!(f, "`{}` is not a valid Unicode code point", v)
            }
            InterpError::NumberRead(token) => {
                write!(f, "could not read a number from input: `{}`", token)
            }
            InterpError::InvalidUtf8 => write!(f, "input is not valid UTF-8"),
            InterpError::Io(e) => write!(f, "i/o error: {}", e),
        }
    }
}

impl std::error::Error for InterpError {}

impl From<std::io::Error> for InterpError {
    fn from(e: std::io::Error) -> Self {
        InterpError::Io(e)
    }
}

/// How a block's execution ended. `Break`/`Continue` propagate outward
/// until the innermost enclosing loop consumes them.
enum Flow {
    Normal,
    Break,
    Continue,
}

/// Byte-level reader that can hand out whole UTF-8 code points and
/// whitespace-delimited number tokens from the same stream.
struct InputReader<R: Read> {
    inner: std::io::BufReader<R>,
}

impl<R: Read> InputReader<R> {
    fn new(inner: R) -> Self {
        InputReader { inner: std::io::BufReader::new(inner) }
    }

    /// Read one UTF-8 code point. Returns `None` at EOF. The next code
    /// point is read as-is, including whitespace.
    fn read_code_point(&mut self) -> Result<Option<char>, InterpError> {
        // Decode the first byte to learn the sequence length.
        let first = loop {
            let buf = self.inner.fill_buf()?;
            if buf.is_empty() {
                return Ok(None); // EOF
            }
            break buf[0];
        };
        let len = utf8_len(first);
        let mut bytes = Vec::with_capacity(len);
        bytes.push(first);
        self.inner.consume(1);
        while bytes.len() < len {
            let buf = self.inner.fill_buf()?;
            if buf.is_empty() {
                return Err(InterpError::InvalidUtf8);
            }
            bytes.push(buf[0]);
            self.inner.consume(1);
        }
        let text = String::from_utf8(bytes).map_err(|_| InterpError::InvalidUtf8)?;
        Ok(Some(text.chars().next().ok_or(InterpError::InvalidUtf8)?))
    }

    /// Read the next whitespace-delimited token. Returns `None` when only
    /// whitespace remains before EOF.
    fn read_token(&mut self) -> Result<Option<String>, InterpError> {
        // Skip leading whitespace.
        loop {
            match self.read_code_point()? {
                None => return Ok(None),
                Some(c) if c.is_whitespace() => continue,
                Some(c) => {
                    let mut token = String::new();
                    token.push(c);
                    // Collect until the next whitespace or EOF.
                    loop {
                        match self.read_code_point()? {
                            None => return Ok(Some(token)),
                            Some(c) if c.is_whitespace() => return Ok(Some(token)),
                            Some(c) => token.push(c),
                        }
                    }
                }
            }
        }
    }
}

fn utf8_len(first: u8) -> usize {
    match first {
        0x00..=0x7F => 1,
        0xC2..=0xDF => 2,
        0xE0..=0xEF => 3,
        0xF0..=0xF4 => 4,
        _ => 1, // invalid lead byte: let from_utf8 report it
    }
}

/// The Gàidheal stack machine.
pub struct Interpreter<R: Read, W: Write> {
    stack: Vec<f64>,
    limit: usize,
    eof: bool,
    input: InputReader<R>,
    out: W,
}

impl<R: Read, W: Write> Interpreter<R, W> {
    pub fn new(input: R, out: W) -> Self {
        Interpreter::with_depth(input, out, 1000)
    }

    pub fn with_depth(input: R, out: W, limit: usize) -> Self {
        Interpreter {
            stack: Vec::new(),
            limit,
            eof: false,
            input: InputReader::new(input),
            out,
        }
    }

    /// Number of values currently on the stack.
    pub fn depth(&self) -> usize {
        self.stack.len()
    }

    /// Consume the interpreter and return the output sink.
    pub fn into_output(self) -> W {
        self.out
    }

    /// The current operand stack, bottom first, top last.
    pub fn stack(&self) -> &[f64] {
        &self.stack
    }

    /// Write a string to the output sink.
    pub fn write_out(&mut self, s: &str) -> Result<(), InterpError> {
        self.out.write_all(s.as_bytes())?;
        Ok(())
    }

    /// Flush the output sink.
    pub fn flush_out(&mut self) -> Result<(), InterpError> {
        self.out.flush()?;
        Ok(())
    }

    /// Read one line of input (without the trailing newline) through the
    /// program's input stream, so REPL program text and `faigh` reads
    /// share a single buffer. Returns `None` only at end of input.
    pub fn read_line(&mut self) -> Result<Option<String>, InterpError> {
        let mut line = String::new();
        loop {
            match self.input.read_code_point()? {
                None => {
                    return Ok(if line.is_empty() { None } else { Some(line) });
                }
                Some('\n') => return Ok(Some(line)),
                Some(c) => line.push(c),
            }
        }
    }

    /// Run a parsed program to completion, flushing output at the end.
    pub fn run(&mut self, program: &Block) -> Result<(), InterpError> {
        self.exec_block(program)?;
        self.out.flush()?;
        Ok(())
    }

    fn exec_block(&mut self, block: &Block) -> Result<Flow, InterpError> {
        for op in block {
            match self.exec_op(op)? {
                Flow::Normal => {}
                flow => return Ok(flow),
            }
        }
        Ok(Flow::Normal)
    }

    fn exec_op(&mut self, op: &Op) -> Result<Flow, InterpError> {
        use Op::*;
        match op {
            Push(n) => self.push(*n)?,
            Copy(i) => {
                let v = self.peek(*i)?;
                self.push(v)?;
            }
            Roll(i) => self.roll(*i)?,
            Dup => {
                let v = self.peek(0)?;
                self.push(v)?;
            }
            Over => {
                let v = self.peek(1)?;
                self.push(v)?;
            }
            StackDepth => {
                let d = self.stack.len() as f64;
                self.push(d)?;
            }
            Swap => self.swap()?,
            Reverse => self.stack.reverse(),
            Tuck => {
                self.need(2)?;
                let b = self.pop()?; // top
                let a = self.pop()?; // second
                self.push(b)?;
                self.push(a)?;
                self.push(b)?;
            }
            Drop => {
                self.pop()?;
            }
            Nip => {
                self.need(2)?;
                let len = self.stack.len();
                self.stack.remove(len - 2);
            }
            Clear => self.stack.clear(),
            Add => self.binary(|a, b| Ok(a + b))?,
            Sub => self.binary(|a, b| Ok(a - b))?,
            Mul => self.binary(|a, b| Ok(a * b))?,
            Div => {
                self.binary(|a, b| {
                    if b == 0.0 {
                        Err(InterpError::DivisionByZero)
                    } else {
                        Ok(a / b)
                    }
                })?
            }
            Rem => {
                self.binary(|a, b| {
                    if b == 0.0 {
                        Err(InterpError::DivisionByZero)
                    } else {
                        Ok(a % b)
                    }
                })?
            }
            Pow => self.binary(|a, b| Ok(a.powf(b)))?,
            Lt => self.compare(|a, b| a < b)?,
            Gt => self.compare(|a, b| a > b)?,
            Eq => self.compare(|a, b| a == b)?,
            PrintNum => {
                let v = self.pop()?;
                writeln!(self.out, "{}", crate::parser::format_number(v))?;
            }
            PrintChar => {
                let v = self.pop()?;
                let c = char::from_u32(v.round() as u32).ok_or(InterpError::InvalidCodePoint(v))?;
                write!(self.out, "{}", c)?;
            }
            ReadNum => {
                match self.input.read_token()? {
                    None => {
                        self.eof = true;
                        self.push(-1.0)?;
                    }
                    Some(token) => {
                        match token.parse::<f64>() {
                            Ok(n) => self.push(n)?,
                            Err(_) => return Err(InterpError::NumberRead(token)),
                        }
                    }
                }
            }
            ReadChar => {
                match self.input.read_code_point()? {
                    None => {
                        self.eof = true;
                        self.push(-1.0)?;
                    }
                    Some(c) => self.push(c as u32 as f64)?,
                }
            }
            EofFlag => {
                let flag = if self.eof { 1.0 } else { 0.0 };
                self.push(flag)?;
            }
            Break => return Ok(Flow::Break),
            Continue => return Ok(Flow::Continue),
            If(stmt) => {
                let cond = self.pop()?;
                let run = match stmt.form {
                    IfForm::Ma => cond != 0.0,
                    IfForm::Mha => cond == 0.0,
                };
                if run {
                    return self.exec_block(&stmt.then_branch);
                } else if let Some(else_branch) = &stmt.else_branch {
                    return self.exec_block(else_branch);
                }
            }
            Loop(stmt) => return self.exec_loop(stmt),
        }
        Ok(Flow::Normal)
    }

    /// Loops. `cuairt` pops its condition BEFORE the body runs (the body
    /// cannot see it); `chuairt` pops AFTER the body; `gcuairt` runs until
    /// `cùl`. `chuìl` skips the rest of the body, but a `chuairt` loop
    /// still consumes its trailing condition first.
    fn exec_loop(&mut self, stmt: &LoopStmt) -> Result<Flow, InterpError> {
        match stmt.kind {
            LoopKind::While => loop {
                let cond = self.pop()?;
                if cond == 0.0 {
                    return Ok(Flow::Normal);
                }
                match self.exec_block(&stmt.body)? {
                    Flow::Break => return Ok(Flow::Normal),
                    Flow::Continue | Flow::Normal => continue,
                }
            },
            LoopKind::DoWhile => loop {
                match self.exec_block(&stmt.body)? {
                    Flow::Break => return Ok(Flow::Normal),
                    Flow::Continue | Flow::Normal => {}
                }
                let cond = self.pop()?;
                if cond == 0.0 {
                    return Ok(Flow::Normal);
                }
            },
            LoopKind::Infinite => loop {
                match self.exec_block(&stmt.body)? {
                    Flow::Break => return Ok(Flow::Normal),
                    Flow::Continue | Flow::Normal => continue,
                }
            },
        }
    }

    // Stack helpers ─────────────────────────────────────────────────────

    fn push(&mut self, v: f64) -> Result<(), InterpError> {
        if self.stack.len() >= self.limit {
            return Err(InterpError::StackOverflow { limit: self.limit });
        }
        self.stack.push(v);
        Ok(())
    }

    fn pop(&mut self) -> Result<f64, InterpError> {
        self.stack.pop().ok_or(InterpError::StackUnderflow)
    }

    fn peek(&self, index: usize) -> Result<f64, InterpError> {
        if index >= self.stack.len() {
            return Err(InterpError::InvalidIndex { index, depth: self.stack.len() });
        }
        Ok(self.stack[self.stack.len() - 1 - index])
    }

    fn need(&self, n: usize) -> Result<(), InterpError> {
        if self.stack.len() < n {
            return Err(InterpError::StackUnderflow);
        }
        Ok(())
    }

    fn swap(&mut self) -> Result<(), InterpError> {
        self.need(2)?;
        let len = self.stack.len();
        self.stack.swap(len - 1, len - 2);
        Ok(())
    }

    /// `gcuir N`: move the Nth element (0 = top) to the top.
    fn roll(&mut self, index: usize) -> Result<(), InterpError> {
        if index >= self.stack.len() {
            return Err(InterpError::InvalidIndex { index, depth: self.stack.len() });
        }
        let len = self.stack.len();
        let v = self.stack.remove(len - 1 - index);
        self.stack.push(v);
        Ok(())
    }

    fn binary<F>(&mut self, f: F) -> Result<(), InterpError>
    where
        F: FnOnce(f64, f64) -> Result<f64, InterpError>,
    {
        let b = self.pop()?;
        let a = self.pop()?;
        self.push(f(a, b)?)
    }

    fn compare<F>(&mut self, f: F) -> Result<(), InterpError>
    where
        F: FnOnce(f64, f64) -> bool,
    {
        let b = self.pop()?;
        let a = self.pop()?;
        self.push(if f(a, b) { 1.0 } else { 0.0 })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse_program;
    use std::io::Cursor;

    fn run(src: &str, input: &str) -> Result<String, InterpError> {
        let program = parse_program(src).unwrap();
        let mut interp =
            Interpreter::new(Cursor::new(input.as_bytes().to_vec()), Vec::new());
        interp.run(&program)?;
        Ok(String::from_utf8(interp.into_output()).unwrap())
    }

    #[test]
    fn arithmetic_and_order() {
        // Binary ops pop b then a and push a op b.
        assert_eq!(run("cuir 2 cuir 3 suim abair", "").unwrap(), "5\n");
        assert_eq!(run("cuir 2 cuir 3 shuim abair", "").unwrap(), "-1\n");
        assert_eq!(run("cuir 2 cuir 3 bsuim abair", "").unwrap(), "6\n");
        assert_eq!(run("cuir 7 cuir 2 dealaich abair", "").unwrap(), "3.5\n");
        assert_eq!(run("cuir 7 cuir 2 dhealaich abair", "").unwrap(), "1\n");
        assert_eq!(run("cuir 2 cuir 3 ndealaich abair", "").unwrap(), "8\n");
    }

    #[test]
    fn comparisons() {
        assert_eq!(run("cuir 1 cuir 2 coimeas abair", "").unwrap(), "1\n");
        assert_eq!(run("cuir 1 cuir 2 choimeas abair", "").unwrap(), "0\n");
        assert_eq!(run("cuir 2 cuir 2 gcoimeas abair", "").unwrap(), "1\n");
    }

    #[test]
    fn print_char_emits_utf8() {
        // 'ò' is U+00F2 = 242; 'à' is U+00E0 = 224.
        assert_eq!(run("cuir 242 n-abair", "").unwrap(), "ò");
    }

    #[test]
    fn mutation_forms() {
        // chuir 0 copies the top; chuir 1 the second; gcuir rolls.
        assert_eq!(run("cuir 4 cuir 5 chuir 1 abair abair", "").unwrap(), "4\n5\n");
        assert_eq!(run("cuir 4 cuir 5 gcuir 1 abair abair", "").unwrap(), "4\n5\n");
        // dtog pushes the depth.
        assert_eq!(run("cuir 1 cuir 2 dtog abair", "").unwrap(), "2\n");
        // bhalairt tucks: [a b] -> [b a b].
        assert_eq!(run("cuir 1 cuir 2 bhalairt abair abair abair", "").unwrap(), "2\n1\n2\n");
        // lheig nips, leig drops, nleig clears.
        assert_eq!(run("cuir 1 cuir 2 lheig abair", "").unwrap(), "2\n");
        // mhalairt reverses the whole stack.
        assert_eq!(run("cuir 1 cuir 2 cuir 3 mhalairt abair abair abair", "").unwrap(), "1\n2\n3\n");
    }

    #[test]
    fn if_else_forms() {
        assert_eq!(run("cuir 1 ma cuir 10 abair criòch", "").unwrap(), "10\n");
        assert_eq!(run("cuir 0 ma cuir 10 abair criòch", "").unwrap(), "");
        assert_eq!(run("cuir 0 mha cuir 10 abair criòch", "").unwrap(), "10\n");
        assert_eq!(run("cuir 0 ma cuir 10 abair no cuir 20 abair criòch", "").unwrap(), "20\n");
        assert_eq!(run("cuir 1 ma cuir 10 abair no cuir 20 abair criòch", "").unwrap(), "10\n");
    }

    #[test]
    fn counted_loop_idiom() {
        // The canonical countdown: gcuairt + explicit zero test.
        let src = "cuir 5 gcuairt chuir 0 mha cuìl criòch tog abair cuir 1 shuim criòch";
        assert_eq!(run(src, "").unwrap(), "5\n4\n3\n2\n1\n");
    }

    #[test]
    fn while_pops_before_body() {
        // cuairt consumes a condition before each iteration and the body
        // cannot see it — so keep TWO copies on entry and re-push the
        // next condition inside the body.
        let src = "cuir 5 tog cuairt chuir 0 abair cuir 1 shuim tog criòch";
        assert_eq!(run(src, "").unwrap(), "5\n4\n3\n2\n1\n");
    }

    #[test]
    fn do_while_pops_after_body() {
        // chuairt prints N..1.
        let src = "cuir 3 chuairt tog abair cuir 1 shuim tog criòch";
        assert_eq!(run(src, "").unwrap(), "3\n2\n1\n");
    }

    #[test]
    fn continue_still_consumes_do_while_condition() {
        // chuìl skips the rest of the body, but the trailing condition
        // pop still happens — otherwise this loop would never terminate.
        let src = concat!(
            "cuir 3 chuairt ",
            "chuir 0 abair ",          // print the counter, keeping it
            "cuir 1 shuim ",            // decrement
            "tog ",                     // sacrificial copy for the condition pop
            "chuir 1 cuir 0 gcoimeas ", // is the next value zero?
            "mha chuìl criòch criòch"   // continue when it is; either way the
                                        // condition pop consumes the sacrificial copy
        );
        assert_eq!(run(src, "").unwrap(), "3\n2\n1\n");
    }

    #[test]
    fn errors() {
        assert!(run("abair", "").is_err()); // underflow
        assert!(run("cuir 1 cuir 0 dealaich", "").is_err()); // division by zero
        assert!(run("chuir 5", "").is_err()); // index out of range
        assert!(run("cuir 1114112 n-abair", "").is_err()); // beyond U+10FFFF
    }

    #[test]
    fn stack_overflow_respects_limit() {
        let program = parse_program("gcuairt cuir 1 criòch").unwrap();
        let mut interp = Interpreter::with_depth(Cursor::new(Vec::new()), Vec::new(), 10);
        assert!(interp.run(&program).is_err());
    }

    #[test]
    fn reads_numbers_and_eof_flag() {
        // faigh reads tokens from anywhere in the input stream.
        let src = "faigh faigh suim abair bhfaigh abair";
        assert!(matches!(run(src, "2 3\n"), Ok(s) if s == "5\n0\n"));
        // After the last token, faigh pushes -1 and bhfaigh reports EOF.
        let src = "faigh leig bhfaigh abair";
        assert!(matches!(run(src, ""), Ok(s) if s == "1\n"));
    }

    #[test]
    fn reads_code_points() {
        let src = "fhaigh abair fhaigh abair fhaigh abair";
        assert_eq!(run(src, "aé").unwrap(), "97\n233\n-1\n");
    }

    #[test]
    fn read_line_shares_the_input_stream() {
        let program = parse_program("faigh abair").unwrap();
        let mut interp = Interpreter::new(Cursor::new(b"40 2\n91\n".to_vec()), Vec::new());
        // faigh reads the first token; a line read returns the rest of
        // the same line, proving they share one buffer.
        interp.run(&program).unwrap();
        let line = interp.read_line().unwrap().unwrap();
        assert_eq!(line.trim(), "2");
        let line = interp.read_line().unwrap().unwrap();
        assert_eq!(line, "91");
        assert!(interp.read_line().unwrap().is_none());
    }

    #[test]
    fn read_line_handles_empty_lines() {
        let mut interp = Interpreter::new(Cursor::new(b"\n\n".to_vec()), Vec::new());
        assert_eq!(interp.read_line().unwrap(), Some(String::new()));
        assert_eq!(interp.read_line().unwrap(), Some(String::new()));
        assert_eq!(interp.read_line().unwrap(), None);
    }

    #[test]
    fn stack_introspection_and_output_helpers() {
        let program = parse_program("cuir 1 cuir 2").unwrap();
        let mut interp = Interpreter::new(Cursor::new(Vec::new()), Vec::new());
        interp.run(&program).unwrap();
        assert_eq!(interp.stack(), &[1.0, 2.0]);
        interp.write_out("hi").unwrap();
        interp.flush_out().unwrap();
        assert_eq!(interp.into_output(), b"hi".to_vec());
    }
}
