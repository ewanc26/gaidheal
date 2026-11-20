# Contributing to Gàidheal

An esoteric stack-based programming language written in Scottish Gaelic. All values are 64-bit doubles on a single operand stack, and every root word comes in three forms selected by initial-consonant mutation: **base** (destructive/primary), **lenited** (variant element), and **eclipsed** (non-destructive/structural) — `cuir` pushes, `chuir` copies, `gcuir` rolls. Tapadh leat airson cuideachaidh!

The reference interpreter is Rust; every program also lowers through readable portable C99 plus `gaidheal_runtime.h`, and the interpreter and C backend are kept in **byte-for-byte differential parity** (`stdout`, `stderr`, and exit codes, including runtime error messages).

## Getting started

```sh
cargo build --release
```

Read `docs/grammar.md` for the full word table first, and `AGENTS.md` for the architecture and contribution invariants.

## Notes for this project

- **Differential parity is the invariant.** Any behaviour change must land in both the Rust interpreter and the C backend, with output identical down to error messages. A PR that makes them disagree will not merge.
- `capabilities.json` / `scripts/check_capabilities.py` is the machine-readable implementation status; update it together with the feature, never after.
- The mutation system (base/lenited/eclipsed) is the language's identity: new words should follow it, with semantics consistent with their form (eclipsed = non-destructive).
- Language accuracy in Gàidhlig matters as much as compiler correctness: new words should be real Gaelic, correctly lenited/eclipsed. If you're not sure, ask in an issue first rather than inventing spelling.
- The VS Code highlighter in `editors/vscode-gaidheal` must keep up with word changes.

## Before opening a PR

- `cargo test` (or the documented test command) passes, and the differential check passes for any changed behaviour.
- Conventional commits; focused PRs; include a sample program exercising the change when you add or alter a word.
- AI-assisted PRs welcome; stand behind every line and run the parity checks yourself.

## Licence

See [LICENSE](LICENSE). Contributions accepted under the same terms.