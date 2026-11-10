# Contributing to Gàidheal

Gàidheal is an esoteric stack-based programming language written in Scottish Gaelic: a single operand stack of 64-bit doubles driven by initial-consonant mutation forms of each root word. The reference interpreter is Rust with no required third-party crates beyond the CLI.

## Development setup

Rust 1.70+ (cargo) is required; Python 3 is needed for the capability matrix check; a C99 compiler (or `clang`) is needed to run the differential tests.

```sh
cargo build
cargo test
./scripts/run_golden_tests.sh target/debug/gaidheal
python3 scripts/check_capabilities.py --language gaidheal --require-complete
python3 scripts/run_differential_tests.py --binary target/debug/gaidheal --cc clang
```

## Working rules

- Read README.md, AGENTS.md, Cargo.toml, CI, and docs/grammar.md before changing language behavior.
- Word spellings live only in `src/builtins.rs` — never hard-code them elsewhere.
- Do not claim a word or behavior as supported until the interpreter and a test cover it; keep `capabilities.json` synchronized and reference test files that exist.
- Keep the interpreter and the C backend in differential parity: after changing either `src/interpreter.rs` or `runtime/gaidheal_runtime.h`, run the differential tests before committing.
- Unsupported syntax must produce a diagnostic with a line number, never a silent no-op.
- Programs in `examples/` and `tests/golden/` carry comments in Gàidhlig only (no Beàrla).
- New examples need a matching golden `.expected` file (and `.input` when they read).
- Use a feature branch and pull request; report exact checks and results.
