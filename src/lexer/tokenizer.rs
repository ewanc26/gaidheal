//! Tokenizer for Gàidheal.
//!
//! Splits source text into words (Gaelic roots, including their accented
//! characters and the hyphen in `n-abair`), number literals, and line
//! information. Comments are `( ... )` and may span lines. The tokenizer
//! itself does not decide where numbers are legal — the parser enforces
//! that a number may only follow `cuir`/`chuir`/`gcuir`.

use std::fmt;

/// A lexical token.
#[derive(Debug, Clone, PartialEq)]
pub enum Token {
    /// A word (root or mutated form, e.g. `cuir`, `mhalairt`, `n-abair`).
    Word(String),
    /// A number literal.
    Number(f64),
    /// End of input.
    Eof,
}

/// A token together with the line it started on (1-based).
#[derive(Debug, Clone, PartialEq)]
pub struct Spanned {
    pub token: Token,
    pub line: usize,
}

/// A lexing failure, with the offending line number.
#[derive(Debug, Clone, PartialEq)]
pub struct LexError {
    pub message: String,
    pub line: usize,
}

impl fmt::Display for LexError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for LexError {}

/// True when `c` can appear inside a word. Gaelic roots use letters
/// (including accented ones such as `ò` and `ù`), apostrophes (`a'`),
/// and the hyphen of `n-abair`.
fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '\'' || c == '-'
}

/// True when `c` can appear inside a number literal being scanned.
fn is_number_char(c: char) -> bool {
    c.is_ascii_digit() || c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-'
}

/// Tokenizer over the whole source, returning the full token list.
pub struct Tokenizer<'a> {
    chars: Vec<char>,
    pos: usize,
    line: usize,
    _src: std::marker::PhantomData<&'a str>,
}

impl<'a> Tokenizer<'a> {
    pub fn new(input: &'a str) -> Self {
        Tokenizer {
            chars: input.chars().collect(),
            pos: 0,
            line: 1,
            _src: std::marker::PhantomData,
        }
    }

    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).copied()
    }

    fn peek2(&self) -> Option<char> {
        self.chars.get(self.pos + 1).copied()
    }

    fn advance(&mut self) -> Option<char> {
        let c = self.peek()?;
        self.pos += 1;
        if c == '\n' {
            self.line += 1;
        }
        Some(c)
    }

    /// Consume a `( ... )` comment. Comments nest and may span lines.
    fn skip_comment(&mut self) -> Result<(), LexError> {
        let start_line = self.line;
        // The opening `(` was already consumed by the caller.
        let mut depth = 1usize;
        while let Some(c) = self.advance() {
            if c == '(' {
                depth += 1;
            } else if c == ')' {
                depth -= 1;
                if depth == 0 {
                    return Ok(());
                }
            }
        }
        Err(LexError {
            message: "unterminated comment: missing `)`".to_string(),
            line: start_line,
        })
    }

    /// A number starts with a digit, or a sign/dot that is immediately
    /// followed by a digit (so `cuir -3` and `cuir .5` parse, while
    /// `n-abair` is left to the word scanner).
    fn number_starts(&self) -> bool {
        match self.peek() {
            Some(c) if c.is_ascii_digit() => true,
            Some(c) if c == '+' || c == '-' || c == '.' => {
                matches!(self.peek2(), Some(d) if d.is_ascii_digit())
            }
            _ => false,
        }
    }

    fn read_number(&mut self) -> Result<Token, LexError> {
        let start_line = self.line;
        let mut text = String::new();
        while let Some(c) = self.peek() {
            if is_number_char(c) {
                text.push(c);
                self.advance();
            } else {
                break;
            }
        }
        text.parse::<f64>()
            .map(Token::Number)
            .map_err(|e| LexError {
                message: format!("invalid number `{}`: {}", text, e),
                line: start_line,
            })
    }

    fn read_word(&mut self) -> Token {
        let mut text = String::new();
        while let Some(c) = self.peek() {
            if is_word_char(c) {
                text.push(c);
                self.advance();
            } else {
                break;
            }
        }
        Token::Word(text)
    }

    /// Tokenize the whole input.
    pub fn tokenize(mut self) -> Result<Vec<Spanned>, LexError> {
        let mut tokens = Vec::new();
        loop {
            // Skip whitespace and comments.
            match self.peek() {
                None => {
                    tokens.push(Spanned { token: Token::Eof, line: self.line });
                    return Ok(tokens);
                }
                Some(c) if c.is_whitespace() => {
                    self.advance();
                    continue;
                }
                Some('(') => {
                    self.advance();
                    self.skip_comment()?;
                    continue;
                }
                Some(')') => {
                    return Err(LexError {
                        message: "unexpected `)` outside a comment".to_string(),
                        line: self.line,
                    });
                }
                Some(_) if self.number_starts() => {
                    let line = self.line;
                    let token = self.read_number()?;
                    tokens.push(Spanned { token, line });
                }
                Some(c) if c.is_alphabetic() || c == '\'' => {
                    let line = self.line;
                    tokens.push(Spanned { token: self.read_word(), line });
                }
                Some(c) => {
                    return Err(LexError {
                        message: format!("unexpected character `{}`", c),
                        line: self.line,
                    });
                }
            }
        }
    }
}

/// Convenience: tokenize a source string.
pub fn tokenize(src: &str) -> Result<Vec<Spanned>, LexError> {
    Tokenizer::new(src).tokenize()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(src: &str) -> Vec<String> {
        tokenize(src)
            .unwrap()
            .into_iter()
            .filter_map(|s| match s.token {
                Token::Word(w) => Some(w),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn tokenizes_simple_words() {
        assert_eq!(words("cuir 5 tog abair"), ["cuir", "tog", "abair"]);
    }

    #[test]
    fn keeps_gaelic_accents_intact() {
        assert_eq!(
            words("criòch cùl mhalairt n-abair a' chùl"),
            ["criòch", "cùl", "mhalairt", "n-abair", "a'", "chùl"]
        );
    }

    #[test]
    fn numbers_include_signs_fractions_and_exponents() {
        let toks = tokenize("cuir -3 cuir 2.5 cuir 1e3 cuir .5").unwrap();
        let nums: Vec<f64> = toks
            .into_iter()
            .filter_map(|s| match s.token {
                Token::Number(n) => Some(n),
                _ => None,
            })
            .collect();
        assert_eq!(nums, [-3.0, 2.5, 1000.0, 0.5]);
    }

    #[test]
    fn comments_span_lines_and_nest() {
        let toks = tokenize("( a 'chiad loidhne\n    an dara loidhne ( nead ) ) cuir 1").unwrap();
        assert_eq!(toks.len(), 3); // cuir, 1, Eof
        assert_eq!(toks[0].line, 2);
    }

    #[test]
    fn unterminated_comment_is_an_error() {
        assert!(tokenize("( gun chrìoch").is_err());
    }

    #[test]
    fn stray_character_is_an_error() {
        assert!(tokenize("cuir 3 @").is_err());
    }

    #[test]
    fn hyphen_alone_is_an_error() {
        assert!(tokenize("cuir - abair").is_err());
    }
}
