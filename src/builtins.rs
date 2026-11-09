//! Canonical word table for Gàidheal.
//!
//! Every root word has three forms selected by initial-consonant mutation:
//! base (destructive/primary), lenited (variant element), and eclipsed
//! (non-destructive/structural). This table is the single source of truth
//! the parser consults; do not hard-code word spellings elsewhere.

/// The semantic operation a Gàidheal word maps to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Word {
    // cuir family: push / copy Nth to top / roll Nth to top (argument follows)
    Push,
    Copy,
    Roll,
    // tog family: dup / over / push stack depth
    Dup,
    Over,
    Depth,
    // malairt family: swap / reverse whole stack / tuck
    Swap,
    Reverse,
    Tuck,
    // leig family: drop / nip / clear
    Drop,
    Nip,
    Clear,
    // suim family: a+b / a−b / a×b
    Add,
    Sub,
    Mul,
    // dealaich family: a÷b / remainder / a^b
    Div,
    Rem,
    Pow,
    // coimeas family: a<b / a>b / a==b (push 1 or 0)
    Lt,
    Gt,
    Eq,
    // abair family: print number+newline / print UTF-8 code point, no newline
    PrintNum,
    PrintChar,
    // faigh family: read number / read code point (−1 at EOF) / push 1 if last read hit EOF
    ReadNum,
    ReadChar,
    EofFlag,
    // ma family: if nonzero / if zero; `no` is the else marker
    If,
    IfZero,
    Else,
    // cuairt family: while (pops before body) / do-while (pops after body) / infinite
    While,
    DoWhile,
    Infinite,
    // control: break / continue; block closer
    Break,
    Continue,
}

/// Look up a word's operation. Returns `None` for unknown words.
pub fn lookup(word: &str) -> Option<Word> {
    use Word::*;
    Some(match word {
        "cuir" => Push,
        "chuir" => Copy,
        "gcuir" => Roll,
        "tog" => Dup,
        "thog" => Over,
        "dtog" => Depth,
        "malairt" => Swap,
        "mhalairt" => Reverse,
        "bhalairt" => Tuck,
        "leig" => Drop,
        "lheig" => Nip,
        "nleig" => Clear,
        "suim" => Add,
        "shuim" => Sub,
        "bsuim" => Mul,
        "dealaich" => Div,
        "dhealaich" => Rem,
        "ndealaich" => Pow,
        "coimeas" => Lt,
        "choimeas" => Gt,
        "gcoimeas" => Eq,
        "abair" => PrintNum,
        "n-abair" => PrintChar,
        "faigh" => ReadNum,
        "fhaigh" => ReadChar,
        "bhfaigh" => EofFlag,
        "ma" => If,
        "mha" => IfZero,
        "no" => Else,
        "cuairt" => While,
        "chuairt" => DoWhile,
        "gcuairt" => Infinite,
        // The canonical break/continue pair is `cùl`/`chuìl`; `cuìl` is
        // accepted as a break alias (both appear in the language examples).
        "cùl" | "cuìl" => Break,
        "chuìl" | "chùl" => Continue,
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_forms_resolve() {
        use Word::*;
        let table = [
            ("cuir", Push), ("chuir", Copy), ("gcuir", Roll),
            ("tog", Dup), ("thog", Over), ("dtog", Depth),
            ("malairt", Swap), ("mhalairt", Reverse), ("bhalairt", Tuck),
            ("leig", Drop), ("lheig", Nip), ("nleig", Clear),
            ("suim", Add), ("shuim", Sub), ("bsuim", Mul),
            ("dealaich", Div), ("dhealaich", Rem), ("ndealaich", Pow),
            ("coimeas", Lt), ("choimeas", Gt), ("gcoimeas", Eq),
            ("abair", PrintNum), ("n-abair", PrintChar),
            ("faigh", ReadNum), ("fhaigh", ReadChar), ("bhfaigh", EofFlag),
            ("ma", If), ("mha", IfZero), ("no", Else),
            ("cuairt", While), ("chuairt", DoWhile), ("gcuairt", Infinite),
            ("cùl", Break), ("chuìl", Continue),
        ];
        for (word, expected) in table {
            assert_eq!(lookup(word), Some(expected), "word `{}`", word);
        }
    }

    #[test]
    fn unknown_words_return_none() {
        assert_eq!(lookup("bearla"), None);
        assert_eq!(lookup("crìoch"), None); // canonical closer is `criòch`, handled by the parser
    }
}
