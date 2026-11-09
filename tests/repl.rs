//! Integration tests for the interactive REPL.

use gaidheal::repl::run_repl;
use std::io::Cursor;

fn repl_output(input: &str) -> String {
    let mut out: Vec<u8> = Vec::new();
    run_repl(Cursor::new(input.as_bytes().to_vec()), &mut out, 1000).unwrap();
    String::from_utf8(out).unwrap()
}

#[test]
fn evaluates_lines_and_shows_the_stack() {
    let out = repl_output("cuir 5\ntog abair\nnleig\n");
    assert!(out.contains("gaidheal> stac(1): 5"), "first line wrong: {}", out);
    // tog dups, abair pops and prints, leaving one value
    assert!(out.contains("> 5\nstac(1): 5\n"), "second line wrong: {}", out);
    // nleig empties the stack: exactly two stack lines in total
    assert_eq!(out.matches("stac(").count(), 2, "unexpected stack lines: {}", out);
}

#[test]
fn multi_line_blocks_wait_for_crioch() {
    let out = repl_output("cuir 9\nma\ncuir 2\nabair\ncriòch\n");
    // after the bare `ma` line, a continuation prompt appears;
    // the block only runs once closed.
    assert!(out.contains("gaidheal>     ...> "), "no continuation: {}", out);
    // ma pops the 9 (nonzero): the body runs and prints 2 once closed
    assert!(out.contains("> 2\n"), "block did not run: {}", out);
}

#[test]
fn parse_errors_reset_the_buffer() {
    let out = repl_output("toc\ncuir 7\n");
    assert!(out.contains("unknown word `toc`"), "error missing: {}", out);
    assert!(out.contains("stac(1): 7"), "state lost after error: {}", out);
}

#[test]
fn stack_persists_across_lines() {
    let out = repl_output("cuir 1\ncuir 2\ncuir 3\n");
    assert!(out.contains("stac(3): 1 2 3"), "stack lost: {}", out);
}

#[test]
fn runtime_errors_keep_the_repl_alive() {
    let out = repl_output("abair\ncuir 4\ndtog\n");
    assert!(out.contains("runtime error: stack underflow"), "error missing: {}", out);
    assert!(out.contains("stac(2): 4 1"), "depth wrong: {}", out);
}

#[test]
fn eof_exits_cleanly() {
    let out = repl_output("");
    assert!(out.contains("Gàidheal REPL"), "banner missing: {}", out);
    assert!(out.trim_end().ends_with("gaidheal>"), "no final prompt: {:?}", out);
}
