# Gàidheal grammar

Gàidheal is an esoteric, stack-based language written in Scottish Gaelic. All
values are 64-bit IEEE 754 doubles on a single operand stack with a
configurable depth limit (default 1000).

## Source form

- **Comments** are `( ... )`. They may span lines and nest.
- **Words** are separated by whitespace. Words may contain letters
  (including accented ones such as `ò` and `ù`), hyphens (`n-abair`), and
  apostrophes (`a'`).
- **Numbers** are decimal with an optional sign, fraction, and exponent:
  `42`, `-3`, `2.5`, `1e3`. A number may only appear immediately after
  `cuir`, `chuir`, or `gcuir`; anywhere else it is a parse error.
- **Blocks** — the bodies of `ma`/`mha`/`no` and the loop forms — always end
  with `criòch`.

## The mutation rule

Each root word has three forms selected by the Gaelic initial-consonant
mutation pattern:

- **base** — the destructive/primary meaning,
- **lenited** — a variant element of the same idea,
- **eclipsed** — the non-destructive/structural meaning.

Binary operations pop `b` (the top), then `a`, and push `a op b`.

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
| `ma B criòch` | `mha B criòch` | `no B criòch` | pop cond, run B if nonzero / if zero / else branch |
| `cuairt B criòch` | `chuairt B criòch` | `gcuairt B criòch` | while / do-while / infinite loop |
| `cùl` | `chuìl` | — | break / continue |

Notes on the table:

- Vowel-initial roots (`abair`) have no visible lenition, so the lenited
  cell does not exist for them.
- `abair`, `n-abair`, `ma`, `mha` and `faigh`, `fhaigh` all **pop** their
  condition or value. Copy first (`chuir 0 abair`) if you still need it.
- `cùl` (break) also accepts the spelling `cuìl`; `chuìl` (continue) also
  accepts `chùl`. Both must appear inside a loop body.
- Indices for `chuir`/`gcuir` must be whole and non-negative, and are
  checked against the current stack depth at runtime.

## Control flow

### Conditionals

`ma` pops its condition and runs the block when it is nonzero; `mha` runs
its block when the popped condition is zero. An `else` branch is introduced
with `no`, placed after the if-block and closing with the block's own
`criòch` — a bare `no` outside that position is a parse error:

```text
ma
    cuir 1 abair
no
    cuir 2 abair
criòch
```

### Loops

- `cuairt` **pops its condition BEFORE each iteration** — the body cannot
  see the condition value.
- `chuairt` runs the body, **then** pops the condition: do-while.
- `gcuairt` loops forever until `cùl`.
- `chuìl` skips the rest of the body, but a `chuairt` loop still consumes
  its trailing condition — the wording of the body must always leave the
  condition value on the stack.

## Critical pitfalls

1. **`cuairt` consumes its condition before the body runs.** Prefer the
   `gcuairt` + explicit-test idiom for counted loops (below).
2. **`abair` and `n-abair` pop their value.** Copy before printing:
   `chuir 0 abair`.
3. **`chuìl` skips the rest of the body.** Put any stack accounting
   (`tog`, decrements, condition pushes) before the `ma … chuìl criòch`
   test, or the loop never terminates.
4. **Comparisons take two stack operands.** Push the literal first:
   `cuir 0 gcoimeas`, never `gcoimeas 0`.
5. **`ma`/`mha` pop their condition.** Dup it first if the body needs it.

## Loop idioms

Countdown (the canonical counted loop):

```text
cuir 5
gcuairt
    chuir 0 mha cuìl criòch      ( break when the counter reaches 0 )
    tog abair                    ( print the counter )
    cuir 1 shuim                 ( decrement )
criòch
```

While with an external value — keep TWO copies on entry (`cuir N tog`),
then inside the body: `chuir 0 abair` (print), `cuir 1 shuim` (update),
`tog` (re-copy for the next check):

```text
cuir 5
cuir 5
cuairt
    chuir 0 abair
    cuir 1 shuim
    tog
criòch
```

Do-while (`chuairt` pops after the body):

```text
cuir 3
chuairt
    tog abair
    cuir 1 shuim
    tog
criòch
```

There are no variables and no strings. Persist state as stack slots
manipulated with `chuir`/`gcuir`, and emit text one code point at a time
with `n-abair` — for example `cuir 242 n-abair` prints `ò`.

## Errors

- Lex errors: unterminated comments, stray characters, invalid numbers.
- Parse errors: numbers outside `cuir`/`chuir`/`gcuir`, unknown words,
  stray `criòch`/`no`, `cùl`/`chuìl` outside a loop, invalid indices,
  unterminated blocks.
- Runtime errors: stack underflow, stack overflow past the depth limit,
  out-of-range stack indices, division or remainder by zero, input that
  is not valid UTF-8, unparseable numbers read with `faigh`, and invalid
  Unicode code points printed with `n-abair`.
