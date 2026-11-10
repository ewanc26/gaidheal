#!/usr/bin/env python3
"""Generate examples/donut_engine.gaidheal: a finite animated torus whose
token stream is byte-identical to the canonical sigi engine.

Byte-parity notes, mirroring the sigi reference engine exactly:

- sigic emits every numeric literal through C++ ostream insertion, which
  prints six significant digits, so the canonical engine really runs with
  TH_STEP = 0.392699, PH_STEP = 0.628319, CB = 0.751806, SB = 0.659385.
- The canonical loops are float-accumulation while-loops: the ring loop
  adds TH_STEP while i < 16 — that is 41 iterations — and the tube loop
  adds PH_STEP while j < 10 — 16 iterations — giving 656 quads per frame.
  Iteration counts are fixed, so this generator bakes the exact cos/sin
  doubles of every accumulated angle, per frame, ring and tube iteration
  index, as base stack slots.  Gaidheal has no loops-over-tables: a lookup
  is an unrolled bisect ladder over the integer countdown counter, and
  every ladder branch is depth-neutral — the selected value replaces a
  placeholder — so `chuir`/`gcuir` literal indices stay correct inside
  `ma`/`no` branches.
- All remaining geometry, projection and shading arithmetic runs at
  program time with only + - * / in exactly the C evaluation order, so
  the doubles match bit for bit.
- The token protocol prints with C percent-g style — six significant
  digits — while gaidheal `abair` prints a double's shortest round-trip
  form.  So the program rounds every printed value to six significant
  digits at runtime — sign, magnitude bucket ladder, remainder, round
  half up, divide back — and `abair` then prints exactly the percent-g
  string.  Rounding ties never occur here; that is asserted below.

Run:    ./target/release/gaidheal examples/donut_engine.gaidheal | ./host_bin
Headless, the host replays the finite stream forever:
  ... | SDL_VIDEODRIVER=dummy ./host_bin --frames 3
"""

import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

R, TUBE = 3.0, 1.25
RING, TUBE_N = 16, 10            # loop bounds, exactly as the canonical
SCALE, OX, OY = 28.0, 120.0, 120.0
SPIN_STEP = 0.05
TILT = 0.72
LIGHT = (0.32, 0.58, 0.75)
FRAMES = 60


def lit_num(v):
    """sigic literal truncation: six significant digits."""
    return float("%g" % round(v, 12))


TH_STEP = lit_num(2 * math.pi / RING)     # 0.392699
PH_STEP = lit_num(2 * math.pi / TUBE_N)   # 0.628319
CB = lit_num(math.cos(TILT))              # 0.751806
SB = lit_num(math.sin(TILT))              # 0.659385

RIT = 41                            # ring iterations: i += TH_STEP while i < 16
TIT = 16                            # tube iterations: j += PH_STEP while j < 10

# ------------------------------------------------ angle accumulation tables
# Exact doubles the canonical engine computes via IEEE accumulation.
F_CA, F_SA = [], []                # per frame: A += SPIN_STEP, then cos/sin
A = 0.0
for _ in range(FRAMES):
    A = A + SPIN_STEP
    F_CA.append(math.cos(A))
    F_SA.append(math.sin(A))

CT1, ST1, CT2, ST2 = [], [], [], []    # cos/sin of i and i + TH_STEP
i = 0.0
for _ in range(RIT):
    CT1.append(math.cos(i))
    ST1.append(math.sin(i))
    CT2.append(math.cos(i + TH_STEP))
    ST2.append(math.sin(i + TH_STEP))
    i = i + TH_STEP

CP1, SP1, CP2 = [], [], []             # cos/sin of j; cos of j + PH_STEP
j = 0.0
for _ in range(TIT):
    CP1.append(math.cos(j))
    SP1.append(math.sin(j))
    CP2.append(math.cos(j + PH_STEP))
    j = j + PH_STEP


def num(v):
    """Emit a double literal that round-trips exactly — Python repr is the
    shortest round-trip decimal, so the interpreter loads the same bits."""
    return repr(v)


class Gh:
    """Emitter with a symbolic stack model: every emitted operation updates
    the model, so `chuir`/`gcuir` literal indices are always correct.

    Branch discipline: every `ma`/`no` pair here is depth-neutral — both
    branches leave the stack depth unchanged (selection branches replace a
    placeholder value).  The model treats branches as executed
    sequentially, which stays index-correct because only depth matters."""

    BINOPS = {"suim", "shuim", "bsuim", "dealaich", "dhealaich", "ndealaich",
              "coimeas", "choimeas", "gcoimeas"}

    def __init__(self):
        self.out = []
        self.stack = []   # tags by absolute position

    def emit(self, word):
        self.out.append(word)
        if word in self.BINOPS:
            self.stack.pop()
            self.stack.pop()
            self.stack.append("r")
        elif word == "tog":            # dup
            self.stack.append(self.stack[-1])
        elif word == "thog":           # over: copy 2nd from top
            self.stack.append(self.stack[-2])
        elif word == "malairt":        # swap top two
            self.stack[-2], self.stack[-1] = self.stack[-1], self.stack[-2]
        elif word in ("leig", "abair", "n-abair"):
            self.stack.pop()
        elif word == "lheig":          # nip: drop 2nd
            del self.stack[-2]
        else:
            raise AssertionError("unmodelled word: " + word)

    def push(self, v):
        self.out.append("cuir " + num(v))
        self.stack.append("lit")

    def copy(self, pos):
        assert 0 <= pos < len(self.stack), (pos, len(self.stack))
        self.out.append("chuir {}".format(len(self.stack) - 1 - pos))
        self.stack.append("c" + str(pos))

    def roll(self, pos):
        assert 0 <= pos < len(self.stack) and pos != len(self.stack) - 1
        self.out.append("gcuir {}".format(len(self.stack) - 1 - pos))
        self.stack.append(self.stack.pop(pos))

    def block(self, word):
        """Emit a control-flow word; `cuairt`/`ma`/`mha` pop their condition
        at runtime, so the model pops it too."""
        self.out.append(word)
        if word in ("cuairt", "ma", "mha"):
            self.stack.pop()

    def model_pop(self):
        """Account for the `cuairt` re-test popping the trailing loop
        condition — no source word, runtime pop only."""
        self.stack.pop()

    def newslot(self, initial=0.0):
        self.push(initial)
        return len(self.stack) - 1               # absolute position

    def setslot(self, pos):
        """Store the value on top into slot pos IN PLACE — the old value must
        not be on top: roll the old slot value up and drop it, then lift
        each displaced element back (repeated gcuir at constant region
        depth), leaving the rest of the stack unshifted."""
        n = len(self.stack)
        self.roll(pos)
        self.emit("leig")
        for _ in range(n - 2 - pos):
            self.roll(pos)


G = Gh()


def comment(text):
    G.out.append("( " + text + " )")


def emit_str(s):
    """Emit a literal token plus the newline separator — code point 10."""
    for ch in s + "\n":
        G.push(ord(ch))
        G.emit("n-abair")


def print_top():
    G.emit("abair")


# --------------------------------------------------------------- selection
def biselect_leaf(table_pos, leaf):
    """Depth-neutral: drop the placeholder on top, copy table slot `leaf`."""
    G.emit("leig")
    G.copy(table_pos[leaf])


def biselect(table_pos, n, ctr_pos, lo, hi):
    """Depth-neutral bisect ladder.  Precondition: a placeholder value P on
    top; leaves replace it with table[idx] where idx = n - ctr and ctr is
    the running countdown in slot `ctr_pos` (ctr is n, n-1, ..., 1 and idx
    runs 0, 1, ... n-1 over the body iterations).

    Branch condition for the lower half — idx <= mid:
        n - ctr <= mid  <=>  ctr > n - mid - 0.5
    """
    assert hi - lo + 1 <= len(table_pos)
    if lo == hi:
        biselect_leaf(table_pos, lo)
        return
    mid = (lo + hi) // 2
    G.push(n - mid - 0.5)
    G.copy(ctr_pos)
    G.emit("coimeas")              # threshold < ctr ?
    G.block("ma")
    biselect(table_pos, n, ctr_pos, lo, mid)
    G.block("no")
    biselect(table_pos, n, ctr_pos, mid + 1, hi)
    G.block("criòch")


def assign_from_table(dest, table_pos, n, ctr_pos):
    """dest := table[n - ctr] via a bisect ladder."""
    G.push(0.0)                    # placeholder consumed by the ladder
    biselect(table_pos, n, ctr_pos, 0, n - 1)
    G.setslot(dest)


# -------------------------------------------------------------- round6 macro
# Round the value on top to six significant digits, in place:
#   neg = v < 0; qm = 1 - 2*neg; a = |v| = v*qm;
#   M = 10^p so that a*M has six integer digits — an unrolled ma/no ladder;
#   w = a*M; frac = rem(w, 1); fl = w - frac; incr = 0.5 < frac;
#   r = fl + incr; out = r/M*qm.
# Exact half ties never occur in this animation — asserted at the bottom.
MAG = [(1e5, 1.0), (1e4, 10.0), (1e3, 100.0), (100.0, 1e3), (10.0, 1e4),
       (1.0, 1e5), (0.1, 1e6), (0.01, 1e7), (0.001, 1e8), (0.0001, 1e9),
       (None, 1e9)]                # below 1e-4: same bucket as 1e-4


def mag_ladder(level):
    """Depth-neutral: replace the |v| value on top with M = 10^p."""
    thr, m = MAG[level]
    if thr is None:
        G.emit("leig")
        G.push(m)
        return
    G.copy(len(G.stack) - 1)      # copy a
    G.push(thr)
    G.emit("choimeas")            # a > thr ?
    G.block("ma")
    G.emit("leig")                # drop a
    G.push(m)
    G.block("no")
    mag_ladder(level + 1)
    G.block("criòch")


def copyd(k):
    """Append a copy of the stack element at distance k — 0 = top."""
    G.copy(len(G.stack) - 1 - k)


def round6():
    """Replace the value on top with itself rounded to six significant
    digits.  Distances are from the top at each emission point:

      [v]
      neg  = v < 0                      [.., v, neg]
      qm   = 1 - 2*neg                  [.., v, neg, qm]
      a    = v*qm                        [.., v, neg, qm, a]
      M    = magnitude ladder            [.., v, neg, qm, a, M]
      w    = a*M                         [.., a, M, w]
      frac = rem(w, 1)                   [.., M, w, frac]
      fl   = w - frac                    [.., w, frac, fl]
      incr = 0.5 < frac                  [.., frac, fl, incr]
      r    = fl + incr                   [.., frac, r]
      res  = r/M                         [.., r, res]
      s    = res*qm                      [.., res, s]
    then nine nips keep only s.
    """
    G.emit("tog")
    G.push(0.0)
    G.emit("coimeas")               # neg = v < 0     [v, neg]
    copyd(0)                        # neg
    G.push(2.0)
    G.emit("bsuim")                 # 2*neg
    G.push(1.0)
    G.emit("malairt")
    G.emit("shuim")                 # qm = 1 - 2*neg  [v, neg, qm]
    copyd(2)                        # v
    copyd(1)                        # qm
    G.emit("bsuim")                 # a = v*qm        [v, neg, qm, a]
    copyd(0)                        # a placeholder
    mag_ladder(0)                   # -> M            [.., a, M]
    copyd(1)                        # a
    copyd(1)                        # M
    G.emit("bsuim")                 # w = a*M         [.., a, M, w]
    copyd(0)                        # w
    G.push(1.0)
    G.emit("dhealaich")             # frac = rem(w,1) [.., M, w, frac]
    copyd(1)                        # w
    copyd(1)                        # frac
    G.emit("shuim")                 # fl = w - frac   [.., w, frac, fl]
    G.push(0.5)
    copyd(2)                        # frac
    G.emit("coimeas")               # incr = 0.5 < frac
    copyd(1)                        # fl (stays on the stack)
    G.emit("suim")                  # r = fl + incr   [.., frac, r]
    copyd(0)                        # r
    copyd(5)                        # M — fl resident at distance 3
    G.emit("dealaich")              # res = r/M
    copyd(0)                        # res
    copyd(8)                        # qm — fl still resident
    G.emit("bsuim")                 # s = res*qm
    for _ in range(10):             # res r fl frac w M a qm neg v
        G.emit("lheig")


def print_rounded():
    round6()
    print_top()


# --------------------------------------------------------------- baked slots
comment("Bòrdan trig: luachan cos agus sin air a bhàthadh a-steach")
comment("leis a' ghineadhar, cruinn dha-rìribh — co-ionnan ri sigi.")
comment("Taghadh le bàta biseach nach bi acrach air doimhne.")

TABLE_SETS = []


def bake_table(values):
    for v in values:
        G.push(v)
    pos = [len(G.stack) - len(values) + k for k in range(len(values))]
    TABLE_SETS.append(len(values))
    return pos


CA_T = bake_table(F_CA)     # cos A gach frèam
SA_T = bake_table(F_SA)     # sin A gach frèam
CT1_T = bake_table(CT1)     # cos theta
ST1_T = bake_table(ST1)     # sin theta
CT2_T = bake_table(CT2)     # cos theta ceum
ST2_T = bake_table(ST2)     # sin theta ceum
CP1_T = bake_table(CP1)     # cos phi
SP1_T = bake_table(SP1)     # sin phi
CP2_T = bake_table(CP2)     # cos phi ceum
NTABS = len(G.stack)

comment("Seadaichean-obrach: trig a chaidh a thaghadh, agus cunntadairean.")
CA = G.newslot()
SA = G.newslot()
CT1 = G.newslot()
ST1 = G.newslot()
CT2 = G.newslot()
ST2 = G.newslot()
CP1 = G.newslot()
SP1 = G.newslot()
CP2 = G.newslot()
CTR_F = G.newslot(float(FRAMES))
CTR_I = G.newslot(float(RIT))
CTR_J = G.newslot(float(TIT))
NSLOTS = len(G.stack)


def reset_slot(pos, value):
    G.push(value)
    G.setslot(pos)


def countdown_cond(pos):
    G.copy(pos)
    G.push(0.0)
    G.emit("choimeas")             # n > 0


def decrement(pos):
    G.copy(pos)
    G.push(1.0)
    G.emit("shuim")
    G.setslot(pos)


# -------------------------------------------------------------- quad corner
def corner(cp, sp, ct, stt):
    """Print the two rounded screen coords of one quad corner."""
    G.copy(cp)
    G.push(TUBE)
    G.emit("bsuim")
    G.push(R)
    G.emit("suim")                      # rad = cosf*TUBE + R
    G.emit("tog")
    G.copy(ct)
    G.emit("bsuim")                     # x = rad*cosTheta
    G.copy(sp)
    G.push(TUBE)
    G.emit("bsuim")                     # y = sinf*TUBE
    rad_pos = len(G.stack) - 3
    G.copy(rad_pos)
    G.copy(stt)
    G.emit("bsuim")                     # z = rad*sinTheta
    x_pos = len(G.stack) - 3
    y_pos = len(G.stack) - 2
    z_pos = len(G.stack) - 1
    # cy = y*ca - z*sa
    G.copy(y_pos)
    G.copy(CA)
    G.emit("bsuim")
    G.copy(z_pos)
    G.copy(SA)
    G.emit("bsuim")
    G.emit("shuim")                      # cy
    cy_pos = len(G.stack) - 1
    # cz = y*sa + z*ca
    G.copy(y_pos)
    G.copy(SA)
    G.emit("bsuim")
    G.copy(z_pos)
    G.copy(CA)
    G.emit("bsuim")
    G.emit("suim")                       # cz
    cz_pos = len(G.stack) - 1
    # px = OX + (x*CB + cz*SB)*SCALE
    G.copy(x_pos)
    G.push(CB)
    G.emit("bsuim")
    G.copy(cz_pos)
    G.push(SB)
    G.emit("bsuim")
    G.emit("suim")
    G.push(SCALE)
    G.emit("bsuim")
    G.push(OX)
    G.emit("suim")                        # px
    print_rounded()
    # py = OY - cy*SCALE
    G.push(OY)
    G.copy(cy_pos)
    G.push(SCALE)
    G.emit("bsuim")
    G.emit("shuim")                       # py
    print_rounded()
    for _ in range(6):                    # rad, x, y, z, cy, cz
        G.emit("leig")


def quad(cp1, sp1, ct1, stt1, cp2, ct2, stt2):
    """Emit one quad line: normal-driven colours kept until after the
    coordinates, exactly like the reference emission order."""
    base_depth = len(G.stack)
    # ny = sp1*ca - cp1*st1*sa
    G.copy(sp1)
    G.copy(CA)
    G.emit("bsuim")
    G.copy(cp1)
    G.copy(stt1)
    G.emit("bsuim")
    G.copy(SA)
    G.emit("bsuim")
    G.emit("shuim")                       # ny
    ny_pos = len(G.stack) - 1
    # nz = sp1*sa + cp1*st1*ca
    G.copy(sp1)
    G.copy(SA)
    G.emit("bsuim")
    G.copy(cp1)
    G.copy(stt1)
    G.emit("bsuim")
    G.copy(CA)
    G.emit("bsuim")
    G.emit("suim")                         # nz
    nz_pos = len(G.stack) - 1
    # nx = cp1*ct1*CB + nz*SB
    G.copy(cp1)
    G.copy(ct1)
    G.emit("bsuim")
    G.push(CB)
    G.emit("bsuim")
    G.copy(nz_pos)
    G.push(SB)
    G.emit("bsuim")
    G.emit("suim")                          # nx
    nx_pos = len(G.stack) - 1
    # lum = (nx*Lr + ny*Lg + nz*Lb + 1)*0.5
    G.copy(nx_pos)
    G.push(LIGHT[0])
    G.emit("bsuim")
    G.copy(ny_pos)
    G.push(LIGHT[1])
    G.emit("bsuim")
    G.emit("suim")
    G.copy(nz_pos)
    G.push(LIGHT[2])
    G.emit("bsuim")
    G.emit("suim")
    G.push(1.0)
    G.emit("suim")
    G.push(0.5)
    G.emit("bsuim")                         # lum
    lum_pos = len(G.stack) - 1
    for mul, add in ((150.0, 80.0), (90.0, 50.0), (60.0, 30.0)):
        G.copy(lum_pos)
        G.push(mul)
        G.emit("bsuim")
        G.push(add)
        G.emit("suim")                       # r / g / b
    # drop the four normals, keeping the three colour values
    while len(G.stack) > base_depth + 3:
        pos = len(G.stack) - 4
        G.roll(pos)
        G.emit("leig")
    emit_str("P")
    for cp, ct, stt in ((cp1, ct1, stt1), (cp2, ct1, stt1),
                        (cp2, ct2, stt2), (cp1, ct2, stt2)):
        corner(cp, sp1, ct, stt)
    # print r, g, b — b is on top
    r_pos = len(G.stack) - 3
    g_pos = len(G.stack) - 2
    G.copy(r_pos)
    print_rounded()                          # r
    G.copy(g_pos)
    print_rounded()                          # g
    print_rounded()                          # b pops it
    G.emit("leig")                           # drop r
    G.emit("leig")                           # drop g


# -------------------------------------------------------------------- main
comment("An t-einnsean donut: sruth ceala-deug co-ionnan ri sigi.")
comment("Cunnt cunntadan sìos le cuairt; tagh trig à bhòrdan.")
comment("Air a ghineadh le scripts/gen_donut_engine.py — FRAMES 60.")

comment("Frèam.")
countdown_cond(CTR_F)
G.block("cuairt")
assign_from_table(CA, CA_T, FRAMES, CTR_F)
assign_from_table(SA, SA_T, FRAMES, CTR_F)
emit_str("F")

comment("Cealla a' chrò — RIT tiotail.")
reset_slot(CTR_I, float(RIT))
countdown_cond(CTR_I)
G.block("cuairt")
assign_from_table(CT1, CT1_T, RIT, CTR_I)
assign_from_table(ST1, ST1_T, RIT, CTR_I)
assign_from_table(CT2, CT2_T, RIT, CTR_I)
assign_from_table(ST2, ST2_T, RIT, CTR_I)

comment("Ceallaich a' phiob — TIT tiotal.")
reset_slot(CTR_J, float(TIT))
countdown_cond(CTR_J)
G.block("cuairt")
assign_from_table(CP1, CP1_T, TIT, CTR_J)
assign_from_table(SP1, SP1_T, TIT, CTR_J)
assign_from_table(CP2, CP2_T, TIT, CTR_J)

comment("Ceithir-cheàrnach le sgàilean.")
quad(CP1, SP1, CT1, ST1, CP2, CT2, ST2)

decrement(CTR_J)
countdown_cond(CTR_J)
G.block("criòch")
G.model_pop()

decrement(CTR_I)
countdown_cond(CTR_I)
G.block("criòch")
G.model_pop()

comment("Fhuaras am frèam air a chrathadh — sgaoil S.")
emit_str("S")
decrement(CTR_F)
countdown_cond(CTR_F)
G.block("criòch")
G.model_pop()

comment("Crìoch an t-srutha.")

assert len(G.stack) == NTABS + 12, \
    "unbalanced model stack: %d" % len(G.stack)

text = "\n".join(G.out) + "\n"
(ROOT / "examples" / "donut_engine.gaidheal").write_text(text, encoding="utf-8")
print("wrote examples/donut_engine.gaidheal: {} lines".format(
    len(text.splitlines())))


# ----------------------------------------------------------- self-verification
def g6(v):
    return "%g" % v


def render_all():
    """Python mirror of the emitted program: exact same value order, used
    to assert no rounding ties occur anywhere in the animation."""
    out = []
    A = 0.0
    for f in range(FRAMES):
        A = A + SPIN_STEP
        ca, sa = math.cos(A), math.sin(A)
        out.append("F")
        i = 0.0
        for _ in range(RIT):
            ct1, st1 = math.cos(i), math.sin(i)
            i2 = i + TH_STEP
            ct2, st2 = math.cos(i2), math.sin(i2)
            j = 0.0
            for _ in range(TIT):
                cp1, sp1 = math.cos(j), math.sin(j)
                j2 = j + PH_STEP
                cp2 = math.cos(j2)
                ny = sp1 * ca - cp1 * st1 * sa
                nz = sp1 * sa + cp1 * st1 * ca
                nx = cp1 * ct1 * CB + nz * SB
                lum = (nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
                       + 1.0) * 0.5
                vals = [lum * 150.0 + 80.0, lum * 90.0 + 50.0,
                        lum * 60.0 + 30.0]
                out.append("P")
                for cp, ct, st_ in ((cp1, ct1, st1), (cp2, ct1, st1),
                                    (cp2, ct2, st2), (cp1, ct2, st2)):
                    rad = cp * TUBE + R
                    x = rad * ct
                    y = sp1 * TUBE
                    z = rad * st_
                    cy = y * ca - z * sa
                    cz = y * sa + z * ca
                    px = (x * CB + cz * SB) * SCALE + OX
                    py = OY - cy * SCALE
                    tie_check(px)
                    tie_check(py)
                    out.append(g6(px))
                    out.append(g6(py))
                for v in vals:
                    tie_check(v)
                    out.append(g6(v))
                j = j + PH_STEP
            i = i + TH_STEP
        out.append("S")
    return out


def tie_check(v):
    """No exact half ties and no %g exponent surprises: the emitted
    runtime rounder is round-half-up, ties would misbehave."""
    M = mag_bound(v)
    w = abs(v) * M
    frac = w - math.floor(w)
    assert abs(frac - 0.5) > 1e-9, "rounding tie at %r" % v
    s = g6(v)
    assert "e" not in s, "exponent form %s for %r" % (s, v)


def mag_bound(v):
    a = abs(v)
    for thr, m in MAG:
        if thr is None or a >= thr:
            return m
    return MAG[-1][1]


if __name__ == "__main__":
    pass

lines = render_all()
print("self-check: rendered {} stream lines, no rounding ties".format(
    len(lines)))
