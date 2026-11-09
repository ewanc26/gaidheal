#!/usr/bin/env sh
# Usage: ./scripts/run_golden_tests.sh [path-to-gaidheal-binary]
# Runs every tests/golden/*.gaidheal through the interpreter and diffs
# stdout+stderr against the matching .expected file (with .input piped to
# stdin when present). Also checks tests/golden/errors/*, which must FAIL
# with output matching their .expected file. Exits non-zero on the first
# mismatch.
set -e

BIN="${1:-target/debug/gaidheal}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
for src in "$DIR"/tests/golden/*.gaidheal; do
    [ -e "$src" ] || break
    name="$(basename "$src" .gaidheal)"
    expected="$DIR/tests/golden/$name.expected"
    [ -f "$expected" ] || { echo "SKIP $name (no .expected file)"; continue; }

    if [ -f "$DIR/tests/golden/$name.input" ]; then
        "$BIN" "$src" < "$DIR/tests/golden/$name.input" > "$TMP/$name.actual" 2>&1
    else
        "$BIN" "$src" > "$TMP/$name.actual" 2>&1
    fi

    if diff -u "$expected" "$TMP/$name.actual" > "$TMP/$name.diff"; then
        echo "PASS $name"
    else
        echo "FAIL $name: output mismatch"
        cat "$TMP/$name.diff"
        fail=1
    fi
done

for src in "$DIR"/tests/golden/errors/*.gaidheal; do
    [ -e "$src" ] || break
    name="$(basename "$src" .gaidheal)"
    expected="$DIR/tests/golden/errors/$name.expected"
    [ -f "$expected" ] || { echo "SKIP $name (no .expected file)"; continue; }

    if "$BIN" "$src" > "$TMP/$name.actual" 2>&1; then
        echo "FAIL $name: expected a runtime or parse error but the program succeeded"
        fail=1
        continue
    fi

    if diff -u "$expected" "$TMP/$name.actual" > "$TMP/$name.diff"; then
        echo "PASS $name"
    else
        echo "FAIL $name: error message mismatch"
        cat "$TMP/$name.diff"
        fail=1
    fi
done

exit $fail
