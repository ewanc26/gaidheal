# AGENTS.md

Guidance for AI coding agents working in **Gàidheal**.

## Project overview

An esoteric stack-based programming language written in Scottish Gaelic. All values are 64-bit doubles on a single operand stack (default depth 1000). Programs manipulate the stack via initial-consonant mutation of root words (base/lenited/eclipsed forms). Control flow: `ma`/`mha`/`no` (if/else), `cuairt`/`chuairt`/`gcuairt` (while/do-while/infinite), `cùl`/`chuìl` (break/continue). Output via `abair` (number + newline) and `n-abair` (UTF-8 code point, no newline). Every block ends with `criòch`.

- Language: Rust
- Default branch: main

## Working rules

- Inspect the README, manifests, CI workflows, and nearby code before editing.
- Preserve existing architecture, naming, formatting, and error-handling conventions.
- Use project scripts for validation; never claim checks you did not run.
- Keep changes scoped and update tests or documentation when behavior changes.
- Use feature branches and pull requests.
- Treat generated files, credentials, deployment configuration, and release metadata as sensitive.

## Architecture notes

- `src/lexer/tokenizer.rs` — tokenizes words, numbers, and comments `( ... )` spanning lines; tracks line numbers for diagnostics
- `src/parser/parser.rs` — parses blocks ending with `criòch`; resolves `ma`/`mha`/`no` and loop nesting; rejects `cùl`/`chuìl` outside loops and numbers outside the `cuir` family
- `src/interpreter.rs` — stack machine over the AST: mutation-form opcodes, arithmetic, comparisons, I/O over abstract `Read`/`Write` streams, break/continue propagation
- `src/builtins.rs` — the canonical word table (`lookup`); the single source of truth for word spellings; do not hard-code words elsewhere
- `src/repl.rs` — interactive REPL over the interpreter's streams: persistent stack, multi-line blocks until their `criòch`, error recovery
- `src/main.rs` — CLI entry: read `.gaidheal` file, parse, interpret; no file starts the REPL; `--tokens`/`--ast` inspection flags; `--stack-depth`

## Language invariants

- Binary ops pop `b`, then `a`, and push `a op b`.
- `cuairt` pops its condition BEFORE each iteration; `chuairt` pops AFTER the body.
- `abair`/`n-abair` and `ma`/`mha` pop values — copy first when a value is needed again.
- Numbers only appear immediately after `cuir`/`chuir`/`gcuir`.
- Write program comments in Gàidhlig inside `( ... )` (no Beàrla in example or test programs).
- Keep `capabilities.json` in sync with implemented behavior and reference test files that exist.
