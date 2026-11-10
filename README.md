# Gàidheal

An esoteric stack-based programming language written in Scottish Gaelic. All values are 64-bit doubles on a single operand stack (default depth 1000). Every root word has three forms selected by initial-consonant mutation: **base** (destructive/primary), **lenited** (variant element), and **eclipsed** (non-destructive/structural) — so `cuir` pushes, `chuir` copies, and `gcuir` rolls.

The reference interpreter is Rust. Every program also lowers through readable portable C99 plus the `gaidheal_runtime.h` runtime and is built with the system C compiler for a native binary; the interpreter and the C backend are kept in byte-for-byte differential parity (`stdout`, `stderr`, and exit codes, including runtime error messages).

```text
( Fàilte dhan t-saoghal )
cuir 70 n-abair
cuir 224 n-abair
cuir 105 n-abair
cuir 108 n-abair
cuir 116 n-abair
cuir 101 n-abair
cuir 33 n-abair
( Fàilte! )
```

Comments are `( ... )` and may span lines. There are no variables and no strings: state lives in stack slots manipulated with `chuir`/`gcuir`, and text is emitted one UTF-8 code point at a time with `n-abair`.

See:

- `docs/grammar.md` for the full word table, control flow, and the loop idioms.
- `capabilities.json` / `scripts/check_capabilities.py` for the machine-readable implementation status.
- `AGENTS.md` for the architecture and contribution invariants.

Gàidheal source highlighting for VS Code is provided in
`editors/vscode-gaidheal`.

## The mutation rule

Binary ops pop `b`, then `a`, and push `a op b`.

| Base | Lenited | Eclipsed | Meaning |
|---|---|---|---|
| `cuir N` | `chuir N` | `gcuir N` | push N / copy Nth element to top (0 = top) / roll Nth element to top |
| `tog` | `thog` | `dtog` | dup / over (copy 2nd) / push stack depth |
| `malairt` | `mhalairt` | `bhalairt` | swap top two / reverse whole stack / tuck (copy top under 2nd) |
| `leig` | `lheig` | `nleig` | drop / nip (drop 2nd) / clear stack |
| `suim` | `shuim` | `bsuim` | a+b / a−b / a×b |
| `dealaich` | `dhealaich` | `ndealaich` | a÷b / remainder / a^b |
| `coimeas` | `choimeas` | `gcoimeas` | push 1 if a<b / a>b / a==b, else 0 |
| `abair` | — | `n-abair` | print top as number + newline / print top as UTF-8 code point, no newline |
| `faigh` | `fhaigh` | `bhfaigh` | read number / read one UTF-8 code point (−1 at EOF) / push 1 if last read hit EOF |
| `ma B criòch` | `mha B criòch` | `no B criòch` | pop cond, run B if nonzero / if zero / else branch (after the if-block, before its `criòch`) |
| `cuairt B criòch` | `chuairt B criòch` | `gcuairt B criòch` | while: pop cond BEFORE each iteration / do-while: pop cond AFTER body / infinite loop |
| `cùl` | `chuìl` | — | break / continue |

Numbers (`42`, `-3`, `2.5`, `1e3`) may only appear immediately after `cuir`, `chuir`, or `gcuir`. Every block ends with `criòch`.

## Build

```sh
cargo build --release
```

Requires cargo 1.70+. The binary is `target/release/gaidheal`.

## Try it

```sh
./target/release/gaidheal examples/failte.gaidheal
./target/release/gaidheal examples/fibonacci.gaidheal
printf '1 2 3 4 5\n' | ./target/release/gaidheal examples/suim.gaidheal
```

Start the interactive REPL (persistent stack, multi-line blocks, `stac(n)` printed after every evaluation):

```text
$ gaidheal
Gàidheal REPL — every block ends with `criòch`. EOF exits.
gaidheal> cuir 5 tog bsuim
stac(1): 25
gaidheal>
```

Program input read by `faigh`/`fhaigh` comes from the same stdin, so typed lines can double as program input.

Inspect a program without running it:

```sh
./target/release/gaidheal examples/failte.gaidheal --tokens
./target/release/gaidheal examples/failte.gaidheal --ast
./target/release/gaidheal examples/failte.gaidheal --stack-depth 4096
```

## Compile to C

```sh
# Emit generated C (reads: readable portable C99 + the runtime header)
./target/release/gaidheal examples/fibonacci.gaidheal --emit-c

# Emit C to a file
./target/release/gaidheal examples/fibonacci.gaidheal --emit-c -o fib.c

# Compile a native binary (keeps the generated C next to it)
./target/release/gaidheal examples/fizzbuzz.gaidheal -o fizzbuzz && ./fizzbuzz

# Compile and run immediately, piping program input
printf '48 18\n' | ./target/release/gaidheal examples/cgd.gaidheal --run

# Use a different C compiler
GAIDHEAL_CC=clang ./target/release/gaidheal examples/cunntas.gaidheal --run
```

## Test

```sh
cargo test
./scripts/run_golden_tests.sh target/debug/gaidheal
python3 scripts/check_capabilities.py --language gaidheal --require-complete
python3 scripts/run_differential_tests.py --binary target/debug/gaidheal --cc clang
```

## Star History

<a href="https://www.star-history.com/?repos=ewanc26%2Fgaidheal&type=date&legend=bottom-right">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ewanc26%2Fgaidheal&type=date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ewanc26%2Fgaidheal&type=date" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ewanc26%2Fgaidheal&type=date" />
  </picture>
</a>
