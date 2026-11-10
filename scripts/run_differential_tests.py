#!/usr/bin/env python3
"""Differential tests: interpreted vs compiled Gaidheal programs.

Usage: scripts/run_differential_tests.py [--binary PATH] [--cc CC]

Every tests/golden/*.gaidheal program (with its .input when present) is run
two ways: through the reference interpreter and through a native binary
compiled from the generated C. Stdout, stderr, and exit codes must match
exactly. Parse-error goldens must fail to compile with identical messages.
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"


def run(binary: str, case: pathlib.Path, input_path, mode: str, tmp: pathlib.Path, cc: str):
    """Run one case; returns (stdout, stderr, returncode) or raises on tool failure."""
    if mode == "interpret":
        cmd = [binary, str(case)]
    else:
        c_path = tmp / (case.stem + ".c")
        emit = subprocess.run(
            [binary, str(case), "--emit-c", "-o", str(c_path)],
            capture_output=True, text=True,
        )
        if emit.returncode != 0:
            # compilation (parse) error: surface it as the run result
            return emit.stdout, emit.stderr, emit.returncode
        bin_path = tmp / case.stem
        build = subprocess.run(
            [cc, "-std=c99", "-O2", str(c_path), "-lm", "-o", str(bin_path)],
            capture_output=True, text=True,
        )
        if build.returncode != 0:
            print(f"FAIL {case.stem}: C compiler failed:\n{build.stderr}", file=sys.stderr)
            sys.exit(1)
        cmd = [str(bin_path)]

    data = input_path.read_bytes() if input_path else b""
    proc = subprocess.run(
        cmd, input=data, capture_output=True,
    )
    return proc.stdout.decode(errors="replace"), proc.stderr.decode(errors="replace"), proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default=str(ROOT / "target" / "debug" / "gaidheal"))
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()

    cases = sorted(GOLDEN.glob("*.gaidheal"))
    for case in sorted((GOLDEN / "errors").glob("*.gaidheal")):
        cases.append(case)
    if not cases:
        print("no golden cases found", file=sys.stderr)
        sys.exit(1)

    failed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        for case in cases:
            input_path = case.with_suffix(".input")
            if not input_path.exists():
                input_path = None

            interp = run(args.binary, case, input_path, "interpret", tmp, args.cc)
            compiled = run(args.binary, case, input_path, "compile", tmp, args.cc)

            if interp == compiled:
                print(f"PASS {case.stem}")
            else:
                failed += 1
                print(f"FAIL {case.stem}:")
                for what, i, c in zip(("stdout", "stderr", "exit code"), interp, compiled):
                    if i != c:
                        print(f"  {what}: interpreted {i!r} != compiled {c!r}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
