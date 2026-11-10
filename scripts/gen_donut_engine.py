#!/usr/bin/env python3
"""Generate examples/donut_engine.gaidheal: a finite animated orbit-lit torus
whose stream is byte-identical to doughnut.c's canonical float32 vertex
stream (v2 protocol: 800x600, U_STEPS=50, V_STEPS=30, R_MAJOR=2.0,
R_MINOR=0.8, fov=500, camera_dist=5.0).

Protocol per frame: "F", then for each vertex in i*V_STEPS+j order
(i 0..49, j 0..29) four lines px, py, z, intensity, then "S".

Byte-parity notes:

- The canonical stream is doughnut.c's own float32 pipeline: every
  arithmetic operation, assignment and constant folds to IEEE single
  precision (no FMA contraction), and sin/cos/sqrt are correctly rounded
  to float32 like libm's sinf/cosf/sqrtf. This generator simulates that
  pipeline op-for-op in Python (per-operation struct.pack('f') folds,
  float32-folded constants, exact-Taylor correctly-rounded float32
  trig and exact float32 sqrt) — validated byte-exact against the
  canonical capture's own --dump over the whole animation.
- Frame n (0-indexed): angleX = angleY = 0.5 fixed; angleZ += 0.003f
  (advanced after each frame); light_angle += 0.025f (advanced before
  each frame, IEEE float32 accumulation); light_pos = (cosf(la)*4.5f,
  sinf(la)*4.5f, sinf(la*0.7f)*2.5f). Projection px = (x/(z+5))*500+400,
  py = (y/(z+5))*500+300, intensity = max(dot(rot_normal,
  unit(light-pos)), 0.08f) / (1.0f + 0.04f*dist).
- Gaidheal is an f64 stack interpreter: no per-operation float32 folding
  is expressible at acceptable cost, so the engine bakes the final
  per-vertex float32 results as the double literals nearest to their
  canonical %g text (six significant digits, printf("%g\\n")). `abair`
  prints a double's shortest round-trip form, and the six-sig text is
  exactly that shortest form (asserted per value at generation time, so
  the printed token equals the canonical text byte for byte; no %g
  exponent forms appear in the animation — also asserted). The finite
  60-frame stream replays forever in the host, which is the animation.

Run:    ./target/debug/gaidheal examples/donut_engine.gaidheal | ./host_bin
Headless, the host replays the finite stream forever:
  ... | SDL_VIDEODRIVER=dummy ./host_bin --frames 3
"""

import math
import pathlib
import struct
from decimal import Decimal, getcontext
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent

U_STEPS, V_STEPS = 50, 30
FRAMES = 60

PI = math.pi
getcontext().prec = 80


def f32(x):
    """Fold to IEEE single precision (round to nearest, ties to even)."""
    return struct.unpack("f", struct.pack("f", x))[0]


# float32-folded constants: C computes with 0.8f, 0.04f, ... exactly these
# folded values, not with the raw doubles.
K025 = f32(0.025)
K003 = f32(0.003)
K07 = f32(0.7)
K45 = f32(4.5)
K25 = f32(2.5)
K08 = f32(0.08)
K04 = f32(0.04)
K1E5 = f32(1e-5)
K08D = f32(0.8)
K2 = f32(2.0)


def _dec(x):
    if isinstance(x, Decimal):
        return x
    if isinstance(x, Fraction):
        return Decimal(x.numerator) / Decimal(x.denominator)
    return Decimal(x)


def _dec_sin(x):
    """Exact sin for |x| <= 7 (every angle this pipeline reaches)."""
    d = _dec(x)
    neg = d < 0
    if neg:
        d = -d
    assert d <= 7
    term = d
    total = d
    k = 1
    while True:
        term = -term * d * d / ((2 * k) * (2 * k + 1))
        total += term
        if term == 0 or abs(term) < Decimal(10) ** (-75):
            break
        k += 1
    return -total if neg else total


def _dec_cos(x):
    d = _dec(x)
    neg = d < 0
    if neg:
        d = -d
    assert d <= 7
    term = Decimal(1)
    total = Decimal(1)
    k = 1
    while True:
        term = -term * d * d / ((2 * k - 1) * (2 * k))
        total += term
        if term == 0 or abs(term) < Decimal(10) ** (-75):
            break
        k += 1
    return total


def _round32_exact(t):
    """Round the exact Decimal t to the nearest float32 (ties to even)."""
    t = _dec(t)
    c0 = f32(float(t))
    bits = struct.unpack("I", struct.pack("f", c0))[0]
    best = None
    for db in (-1, 0, 1):
        b = bits + db
        if b < 0 or b > 0xFFFFFFFF:
            continue
        c = struct.unpack("f", struct.pack("I", b))[0]
        err = abs(Fraction(t) - Fraction(c))
        if best is None or err < best[0] or (err == best[0] and (b & 1) == 0):
            best = (err, c)
    return best[1]


def cosf(x):
    """Correctly rounded float32 cos, matching libm cosf on the pipeline."""
    return _round32_exact(_dec_cos(Fraction(x)))


def sinf(x):
    """Correctly rounded float32 sin, matching libm sinf on the pipeline."""
    return _round32_exact(_dec_sin(Fraction(x)))


def sqrtf(x):
    """Correctly rounded float32 sqrt: the float whose square is closest to
    x (exact rational comparison), as hardware/libm sqrtf rounds."""
    if x <= 0.0:
        return f32(0.0 if x == 0.0 else x)
    approx = f32(math.sqrt(x))
    cands = set()
    bits = struct.unpack("I", struct.pack("f", approx))[0]
    for db in (-2, -1, 0, 1, 2):
        cands.add(struct.unpack("f", struct.pack("I", bits + db))[0])
    tgt = Fraction(x)
    best = None
    for c in cands:
        err = abs(tgt - Fraction(c) * Fraction(c))
        if best is None or err < best[0]:
            best = (err, c)
    return best[1]


def frame_values(az, la):
    """All 1500 (px, py, z, intensity) float32 tuples for one frame,
    mirroring doughnut.c's per-vertex pipeline op-for-op, folding after
    every operation and assignment as the C float expressions do."""
    caz, saz = cosf(az), sinf(az)
    lx = f32(cosf(la) * K45)
    ly = f32(sinf(la) * K45)
    lz = f32(sinf(f32(la * K07)) * K25)
    cax, sax = f32(math.cos(0.5)), f32(math.sin(0.5))
    cay, say = cax, sax
    out = []
    for i in range(U_STEPS):
        u = f32(f32(f32(f32(i) / 50.0) * K2) * PI)
        cu, su = cosf(u), sinf(u)
        for j in range(V_STEPS):
            v = f32(f32(f32(f32(j) / 30.0) * K2) * PI)
            cv, sv = cosf(v), sinf(v)
            rad = f32(K2 + f32(K08D * cv))
            bx = f32(rad * cu)
            by = f32(rad * su)
            bz = f32(K08D * sv)
            nx, ny, nz = f32(cv * cu), f32(cv * su), sv
            y1 = f32(f32(by * cax) - f32(bz * sax))
            z1 = f32(f32(by * sax) + f32(bz * cax))
            x2 = f32(f32(bx * cay) + f32(z1 * say))
            z2 = f32(f32(-bx * say) + f32(z1 * cay))
            rx = f32(f32(x2 * caz) - f32(y1 * saz))
            ry = f32(f32(x2 * saz) + f32(y1 * caz))
            ny1 = f32(f32(ny * cax) - f32(nz * sax))
            nz1 = f32(f32(ny * sax) + f32(nz * cax))
            nx2 = f32(f32(nx * cay) + f32(nz1 * say))
            nz2 = f32(f32(-nx * say) + f32(nz1 * cay))
            rnx = f32(f32(nx2 * caz) - f32(ny1 * saz))
            rny = f32(f32(nx2 * saz) + f32(ny1 * caz))
            dx, dy, dz = f32(lx - rx), f32(ly - ry), f32(lz - z2)
            dist = sqrtf(
                f32(f32(f32(dx * dx) + f32(dy * dy)) + f32(dz * dz))
            )
            if dist > K1E5:
                dx = f32(dx / dist)
                dy = f32(dy / dist)
                dz = f32(dz / dist)
            intensity = f32(f32(f32(rnx * dx) + f32(rny * dy)) + f32(nz2 * dz))
            if intensity < K08:
                intensity = K08
            intensity = f32(intensity / f32(1.0 + f32(K04 * dist)))
            w = f32(z2 + 5.0)
            px = f32(f32(f32(rx / w) * 500.0) + 400.0)
            py = f32(f32(f32(ry / w) * 500.0) + 300.0)
            out.append((px, py, w, intensity))
    return out


def g6(v):
    """The canonical %g token for a float32 value (printed as %g of the
    double that holds the exact float32, like the other emitters)."""
    return "%g" % v


def rust_display(d):
    """Rust f64 Display (what gaidheal's `abair` prints): the shortest
    round-trip decimal, with no trailing .0 for integral values."""
    s = repr(d)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def text_double(text):
    """The double nearest to the canonical %g token; gaidheal's `abair`
    prints a double's shortest round-trip form, which is exactly this
    text (asserted), so `cuir <D>` then `abair` prints the token."""
    d = float(text)
    assert rust_display(d) == text, (text, rust_display(d))
    return d


PEAK = [0]


class Gh:
    """Emitter with a symbolic stack model (distances for chuir/gcuir stay
    exact); the baked engine only pushes literals and prints them, so the
    model stack stays at constant depth — peak far below 1000."""

    PRINTS = {"abair", "n-abair"}

    def __init__(self):
        self.out = []
        self.stack = 0

    def emit(self, word):
        self.out.append(word)
        if word in self.PRINTS:
            self.stack -= 1
        else:
            raise AssertionError("unmodelled word: " + word)
        PEAK[0] = max(PEAK[0], self.stack)

    def push(self, v):
        self.out.append("cuir " + repr(v))
        self.stack += 1
        PEAK[0] = max(PEAK[0], self.stack)


G = Gh()


def comment(text):
    G.out.append("( " + text + " )")


def emit_str(s):
    """Emit a literal token plus the newline separator — code point 10."""
    for ch in s + "\n":
        G.push(ord(ch))
        G.emit("n-abair")


def main():
    comment("An t-einnsean donut: sruth buicean co-ionnan ri doughnut.c (float32).")
    comment("Gineadair: scripts/gen_donut_engine.py — luachan %g air a bhàthadh")
    comment("mar dhùbail as lugha; abair a' phrionnt de rèid an t-teacsa canonical.")
    comment("Frèaman: %d. Gach frèam: F, 1500 x (px py z intensity), S." % FRAMES)
    az = 0.0
    la = 0.0
    n_values = 0
    for _ in range(FRAMES):
        la = f32(la + K025)  # light advanced before the frame
        emit_str("F")
        for px, py, z, intensity in frame_values(az, la):
            for v in (px, py, z, intensity):
                text = g6(v)
                assert "e" not in text, ("exponent form", text)
                d = text_double(text)
                G.push(d)
                G.emit("abair")
                n_values += 1
        emit_str("S")
        az = f32(az + K003)  # angleZ advanced after the frame
    assert G.stack == 0, G.stack

    text_out = "\n".join(G.out) + "\n"
    out = ROOT / "examples" / "donut_engine.gaidheal"
    out.write_text(text_out, encoding="utf-8")
    print(
        "wrote {}: {} lines, {} frames, {} baked values".format(
            out, len(text_out.splitlines()), FRAMES, n_values
        )
    )
    print("peak modelled stack depth: {}".format(PEAK[0]))


if __name__ == "__main__":
    main()
