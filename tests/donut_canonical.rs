//! Canonical donut stream parity: the first eight frames emitted by
//! examples/donut_engine.gaidheal must be byte-identical to the canonical
//! sigi engine stream vendored in tests/fixtures/donut_canonical_8f.txt.
//!
//! The example animates 60 frames of 656 quads each; only the first eight
//! frames are compared, matching the fixture.

use std::io::Cursor;

const FRAMES_COMPARE: usize = 8;
const LINES_PER_FRAME: usize = 7874; // 656 quads x 12 lines + F + S

#[test]
fn donut_engine_first_8_frames_match_canonical() {
    let src = include_str!("../examples/donut_engine.gaidheal");
    let input = Cursor::new(Vec::<u8>::new());
    let mut out: Vec<u8> = Vec::new();
    gaidheal::run_source(src, input, &mut out)
        .expect("donut engine program must run cleanly");

    let want_bytes = include_bytes!("fixtures/donut_canonical_8f.txt");
    let want = std::str::from_utf8(want_bytes).expect("fixture is UTF-8");
    let want_lines: Vec<&str> = want.lines().collect();
    assert_eq!(
        want_lines.len(),
        FRAMES_COMPARE * LINES_PER_FRAME,
        "fixture must hold {} frames of the canonical stream",
        FRAMES_COMPARE
    );

    let got = String::from_utf8(out).expect("engine output is UTF-8");
    let got_lines: Vec<&str> = got
        .lines()
        .take(FRAMES_COMPARE * LINES_PER_FRAME)
        .collect();
    assert_eq!(got_lines.len(), FRAMES_COMPARE * LINES_PER_FRAME,
        "engine produced fewer than {} frames", FRAMES_COMPARE);
    let first_mismatch = got_lines
        .iter()
        .zip(want_lines.iter())
        .position(|(a, b)| a != b)
        .map(|i| i + 1)
        .unwrap_or(0);
    assert_eq!(
        got_lines, want_lines,
        "donut engine stream differs from the canonical, first mismatch at line {}",
        first_mismatch
    );
}
