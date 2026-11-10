//! Canonical donut stream parity (v2 vertex protocol): the first two
//! frames emitted by examples/donut_engine.gaidheal must be
//! byte-identical to the canonical sigi engine stream vendored in
//! tests/fixtures/donut_canonical_v2_2f.txt.
//!
//! Protocol per frame: "F", then for each of the 1500 torus vertices
//! (i*V_STEPS+j order, i in 0..49, j in 0..29) four lines px, py, z,
//! intensity, then "S" — mirrors the renderer in doughnut.c.  The
//! example animates 60 frames; only the first two frames are compared,
//! matching the fixture (the fixture is the captured canonical prefix).

use std::io::Cursor;

const FRAMES_COMPARE: usize = 2;
const LINES_PER_FRAME: usize = 6002; // 1500 vertices x 4 lines + F + S

#[test]
fn donut_engine_first_2_frames_match_canonical_v2() {
    let src = include_str!("../examples/donut_engine.gaidheal");
    let input = Cursor::new(Vec::<u8>::new());
    let mut out: Vec<u8> = Vec::new();
    gaidheal::run_source(src, input, &mut out)
        .expect("donut engine program must run cleanly");

    let want_bytes = include_bytes!("fixtures/donut_canonical_v2_2f.txt");
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
