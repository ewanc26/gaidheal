#!/usr/bin/env python3
"""Generate examples/donut_engine.gaidheal: a finite animated orbit-lit torus
whose stream is byte-identical to the canonical sigi engine (v2 vertex
protocol, cf. doughnut.c: 800x600, U_STEPS=50, V_STEPS=30, R_MAJOR=2.0,
R_MINOR=0.8, fov=500, camera_dist=5.0).

Protocol per frame: "F", then for each vertex in i*V_STEPS+j order
(i 0..49, j 0..29) four lines px, py, z, intensity, then "S".

Byte-parity notes, mirroring the sigi reference engine exactly:

- Frame n (0-indexed): angleX = angleY = 0.5 fixed; angleZ = 0.003*n
  (advanced after each frame); light_angle = 0.025*(n+1) (advanced before
  each frame, by IEEE accumulation).  The sigi generator's constants are
  round(cos/sin(0.5), 12), round(2*pi/50, 12) and round(2*pi/30, 12),
  parsed at full double precision by sigic (verified against the captured
  canonical stream /tmp/canonical_donut_v2_2f.stream).
- The canonical engine computes trig at runtime in double via libm, so
  this generator bakes the exact cos/sin doubles of every reachable
  angle — per frame (angleZ, light_angle, 0.7*light_angle) and per
  torus step (i*U_STEP, j*V_STEP) — as base stack slots.  Gaidheal has
  no loops-over-tables: a lookup is an unrolled bisect ladder over the
  integer countdown counter, and every ladder branch is depth-neutral
  (the selected value replaces a placeholder), so `chuir`/`gcuir`
  literal indices stay correct inside `ma`/`no` branches.
- All remaining arithmetic runs at program time with only the gaidheal
  primitives (+ - * / remainder power comparison) in exactly the sigi
  op order, so the doubles match bit for bit.  sqrt is power 0.5:
  f64::powf(x, 0.5) == f64::sqrt(x) for every distance in the whole
  animation (checked over all 60 frames x 1500 vertices).
- The protocol prints with C percent-g style — six significant digits —
  while gaidheal `abair` prints a double's shortest round-trip form.
  So the program rounds every printed value to six significant digits
  at runtime — sign, magnitude bucket ladder, remainder, round half up,
  divide back — and `abair` then prints exactly the percent-g string.
  Rounding ties never occur here; that is asserted below, as is the
  dist > 1e-5 normalisation precondition and the %g exponent freedom.

Run:    ./target/release/gaidheal examples/donut_engine.gaidheal | ./host_bin
Headless, the host replays the finite stream forever:
  ... | SDL_VIDEODRIVER=dummy ./host_bin --frames 3
"""

import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

U_STEPS, V_STEPS = 50, 30
CAM_DIST = 5.0           # doughnut.c camera_dist
FOV = 500.0
AZ_STEP = 0.003           # angleZ per frame (after)
LA_STEP = 0.025           # light_angle per frame (before)
FRAMES = 60

CAX = round(math.cos(0.5), 12)              # sigi: round(cos(0.5), 12)
SAX = round(math.sin(0.5), 12)
U_STEP = round(2 * math.pi / U_STEPS, 12)
V_STEP = round(2 * math.pi / V_STEPS, 12)

# ------------------------------------------------ angle accumulation tables
# Exact doubles the canonical engine computes via libm trig on the
# IEEE-accumulated angles.
CAZ, SAZ = [], []           # per frame: angleZ (starts 0, advances after)
az = 0.0
for _ in range(FRAMES):
    CAZ.append(math.cos(az))
    SAZ.append(math.sin(az))
    az = az + AZ_STEP

CL, SL, SL07 = [], [], []   # per frame: light_angle (advances before)
la = 0.0
for _ in range(FRAMES):
    la = la + LA_STEP
    CL.append(math.cos(la))
    SL.append(math.sin(la))
    SL07.append(math.sin(la * 0.7))

CU, SU = [], []             # cos/sin(i * U_STEP), i = 0..49
for i in range(U_STEPS):
    CU.append(math.cos(i * U_STEP))
    SU.append(math.sin(i * U_STEP))

CV, SV = [], []             # cos/sin(j * V_STEP), j = 0..29
for j in range(V_STEPS):
    CV.append(math.cos(j * V_STEP))
    SV.append(math.sin(j * V_STEP))


def num(v):
    """Emit a double literal that round-trips exactly — Python repr is the
    shortest round-trip decimal, so the interpreter loads the same bits."""
    return repr(v)


class Gh:
    """Emitter with a symbolic stack model: every emitted word updates a
    model stack of tagged entries, so copy/roll indices (`chuir`/`gcuir`
    argument literals are distances from the stack top) stay exact even
    though the values are unknown at generation time."""

    BINOPS = {"suim", "shuim", "bsuim", "dealaich", "dhealaich",
              "ndealaich", "coimeas", "choimeas", "gcoimeas"}

    def __init__(self):
        self.out = []
        self.stack = []

    def emit(self, word):
        self.out.append(word)
        if word in self.BINOPS:
            self.stack.pop()
            self.stack.pop()
            self.stack.append("r")
        elif word == "tog":            # dup
            self.stack.append(self.stack[-1])
        elif word == "thog":           # over: copy 2nd from Top
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


def assign_from_table(dest, table_pos, n, ctr_pos, mul=None):
    """dest := table[n - ctr] via a bisect ladder; optionally * mul."""
    G.push(0.0)                    # placeholder consumed by the ladder
    biselect(table_pos, n, ctr_pos, 0, n - 1)
    if mul is not None:
        G.push(mul)
        G.emit("bsuim")
    G.setslot(dest)


# -------------------------------------------------------------- round6 macro
# Round the value on top to six significant digits, in place:
#   neg = v < 0; qm = 1 - 2*neg; a = |v| = v*qm;
#   M = 10^p so that a*M has six integer digits — an unrolled ma/no ladder;
#   w = a*M; frac = rem(w, 1); fl = w - frac; incr = 0.5 < frac;
#   r = fl + incr; out = r/M*qm.
# Exact half ties never occur in this animation — asserted at the bottom.
# Negative values rounded: py can be negative (offscreen vertices) — the
# sign handling below covers them.
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
    then ten nips keep only s.
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
    copyd(5)                        # M — fl stays resident
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


CAZ_T = bake_table(CAZ)     # cos angleZ gach frèam
SAZ_T = bake_table(SAZ)     # sin angleZ gach frèam
CL_T = bake_table(CL)       # cos light_angle gach frèam
SL_T = bake_table(SL)       # sin light_angle gach frèam
SL07_T = bake_table(SL07)   # sin(0.7*light_angle) gach frèam
CU_T = bake_table(CU)       # cos(i*U_STEP)
SU_T = bake_table(SU)       # sin(i*U_STEP)
CV_T = bake_table(CV)       # cos(j*V_STEP)
SV_T = bake_table(SV)       # sin(j*V_STEP)
NTABS = len(G.stack)

comment("Seadaichean-obrach: trig a chaidh a thaghadh, agus cunntadairean.")
CAZ = G.newslot()
SAZ = G.newslot()
LX = G.newslot()            # cos(la)*4.5
LY = G.newslot()            # sin(la)*4.5
LZ = G.newslot()            # sin(0.7*la)*2.5
CU = G.newslot()
SU = G.newslot()
CV = G.newslot()
SV = G.newslot()
CTR_F = G.newslot(float(FRAMES))
CTR_I = G.newslot(float(U_STEPS))
CTR_J = G.newslot(float(V_STEPS))
NSLOTS = len(G.stack)

PEAK = [0]


def check_peak():
    PEAK[0] = max(PEAK[0], len(G.stack))


def reset_slot(pos, value):
    G.push(value)
    G.setslot(pos)


def countdown_cond(pos):
    G.copy(pos)
    G.push(0.0)
    check_peak()
    G.emit("choimeas")             # n > 0


def decrement(pos):
    G.copy(pos)
    G.push(1.0)
    G.emit("shuim")
    G.setslot(pos)


# -------------------------------------------------------- one torus vertex
def vertex():
    """Compute and print px, py, z, intensity for one i,j torus vertex,
    mirroring the sigi engine's op order exactly (see render_all below).

    Stack layout while computing (offsets from NSLOTS):
       0 rad   1 bx   2 by   3 bz   4 nx   5 ny
       6 y1    7 z1   8 x2   9 z2   (position rotation)
      10 rx   11 ry
      12 y1n 13 z1n 14 x2n 15 z2n  (normal rotation)
      16 rnx 17 rny
      18 dx  19 dy  20 dz  21 dist  22 ndx 23 ndy 24 ndz
      25 intensity  26 intensity'  27 w
    """
    H = NSLOTS                      # stack height before the temps

    def c(off):                     # copy the temp at offset off
        G.copy(H + off)

    def pc(v):
        G.push(v)

    check_peak()

    # torus position and normal, doughnut.c generate_torus()
    G.copy(CV)
    pc(0.8)
    G.emit("bsuim")
    pc(2.0)
    G.emit("suim")                  # 0: rad = 2.0 + 0.8*cv
    c(0)
    G.copy(CU)
    G.emit("bsuim")                # 1: bx = rad*cu
    c(0)
    G.copy(SU)
    G.emit("bsuim")                # 2: by = rad*su
    pc(0.8)
    G.copy(SV)
    G.emit("bsuim")                # 3: bz = 0.8*sv
    G.copy(CV)
    G.copy(CU)
    G.emit("bsuim")                # 4: nx = cv*cu
    G.copy(CV)
    G.copy(SU)
    G.emit("bsuim")                # 5: ny = cv*su

    # rotate_vector(pos, ax, ay, az) — X, then Y, then Z
    c(2)
    pc(CAX)
    G.emit("bsuim")
    c(3)
    pc(SAX)
    G.emit("bsuim")
    G.emit("shuim")                # 6: y1 = by*cax - bz*sax
    c(2)
    pc(SAX)
    G.emit("bsuim")
    c(3)
    pc(CAX)
    G.emit("bsuim")
    G.emit("suim")                 # 7: z1 = by*sax + bz*cax
    c(1)
    pc(CAX)
    G.emit("bsuim")
    c(7)
    pc(SAX)
    G.emit("bsuim")
    G.emit("suim")                 # 8: x2 = bx*cax + z1*sax
    c(7)
    pc(CAX)
    G.emit("bsuim")
    c(1)
    pc(SAX)
    G.emit("bsuim")
    G.emit("shuim")                # 9: z2 = z1*cax - bx*sax
    c(8)
    G.copy(CAZ)
    G.emit("bsuim")
    c(6)
    G.copy(SAZ)
    G.emit("bsuim")
    G.emit("shuim")                # 10: rx = x2*caz - y1*saz
    c(8)
    G.copy(SAZ)
    G.emit("bsuim")
    c(6)
    G.copy(CAZ)
    G.emit("bsuim")
    G.emit("suim")                 # 11: ry = x2*saz + y1*caz

    # rotate_vector(normal, ...) — same tilt and spin
    c(5)
    pc(CAX)
    G.emit("bsuim")
    G.copy(SV)
    pc(SAX)
    G.emit("bsuim")
    G.emit("shuim")                # 12: y1n = ny*cax - sv*sax
    c(5)
    pc(SAX)
    G.emit("bsuim")
    G.copy(SV)
    pc(CAX)
    G.emit("bsuim")
    G.emit("suim")                 # 13: z1n = ny*sax + sv*cax
    c(4)
    pc(CAX)
    G.emit("bsuim")
    c(13)
    pc(SAX)
    G.emit("bsuim")
    G.emit("suim")                 # 14: x2n = nx*cax + z1n*sax
    c(13)
    pc(CAX)
    G.emit("bsuim")
    c(4)
    pc(SAX)
    G.emit("bsuim")
    G.emit("shuim")                # 15: z2n = z1n*cax - nx*sax
    c(14)
    G.copy(CAZ)
    G.emit("bsuim")
    c(12)
    G.copy(SAZ)
    G.emit("bsuim")
    G.emit("shuim")                # 16: rnx = x2n*caz - y1n*saz
    c(14)
    G.copy(SAZ)
    G.emit("bsuim")
    c(12)
    G.copy(CAZ)
    G.emit("bsuim")
    G.emit("suim")                 # 17: rny = x2n*saz + y1n*caz

    # orbiting point light: direction, distance, normalisation
    G.copy(LX)
    c(10)
    G.emit("shuim")                # 18: dx = lx - rx
    G.copy(LY)
    c(11)
    G.emit("shuim")                # 19: dy = ly - ry
    G.copy(LZ)
    c(9)
    G.emit("shuim")                # 20: dz = lz - z2
    c(18)
    c(18)
    G.emit("bsuim")
    c(19)
    c(19)
    G.emit("bsuim")
    G.emit("suim")                 # dx*dx + dy*dy
    c(20)
    c(20)
    G.emit("bsuim")
    G.emit("suim")                 # .. + dz*dz
    pc(0.5)
    G.emit("ndealaich")            # 21: dist = sqrt via power 0.5
    c(18)
    c(21)
    G.emit("dealaich")             # 22: ndx = dx/dist
    c(19)
    c(21)
    G.emit("dealaich")             # 23: ndy = dy/dist
    c(20)
    c(21)
    G.emit("dealaich")             # 24: ndz = dz/dist

    # Lambert + 0.08 ambient floor, in place at offset 25
    c(16)
    c(22)
    G.emit("bsuim")
    c(17)
    c(23)
    G.emit("bsuim")
    G.emit("suim")
    c(15)
    c(24)
    G.emit("bsuim")
    G.emit("suim")                 # 25: raw intensity
    c(25)                          # copy of raw = condition
    pc(0.08)
    G.emit("coimeas")              # raw < 0.08 ?
    G.block("ma")                  # pops the flag; the raw intensity is on top
    G.emit("leig")                 # drop the raw value
    pc(0.08)                       # .. and push 0.08 in its place
    G.block("no")                  # else: keep the raw value
    G.block("criòch")

    # 26: denom = 1.0 + 0.04*dist ; 27: intensity' = intensity / denom
    c(21)
    pc(0.04)
    G.emit("bsuim")
    pc(1.0)
    G.emit("suim")                 # 26: denom
    c(25)
    c(26)
    G.emit("dealaich")             # 27: intensity'
    # 28: w = z2 + 5.0
    c(9)
    pc(5.0)
    G.emit("suim")                 # 28: w

    # projection and printing: px, py, z, intensity
    c(10)
    c(28)
    G.emit("dealaich")
    pc(500.0)
    G.emit("bsuim")
    pc(400.0)
    G.emit("suim")                 # px
    print_rounded()
    c(11)
    c(28)
    G.emit("dealaich")
    pc(500.0)
    G.emit("bsuim")
    pc(300.0)
    G.emit("suim")                 # py
    print_rounded()
    c(28)
    print_rounded()                # z = w
    c(27)
    print_rounded()                # intensity

    # drop the 28 remaining temps (0..27); the w copy was printed in place
    for _ in range(len(G.stack) - NSLOTS):
        G.emit("leig")
    assert len(G.stack) == NSLOTS, len(G.stack)


# -------------------------------------------------------------------- main
comment("An t-einnsean donut: sruth buicean co-ionnan ri sigi (doughnut.c).")
comment("Cunnt cunntadan sìos le cuairt; tagh trig à bhòrdan.")
comment("Air a ghineadh le scripts/gen_donut_engine.py — FRAMES %d." % FRAMES)
comment("Frèam.")
countdown_cond(CTR_F)
G.block("cuairt")
assign_from_table(CAZ, CAZ_T, FRAMES, CTR_F)
assign_from_table(SAZ, SAZ_T, FRAMES, CTR_F)
assign_from_table(LX, CL_T, FRAMES, CTR_F, mul=4.5)
assign_from_table(LY, SL_T, FRAMES, CTR_F, mul=4.5)
assign_from_table(LZ, SL07_T, FRAMES, CTR_F, mul=2.5)
emit_str("F")

comment("Lùb U — U_STEPS ceuma.")
reset_slot(CTR_I, float(U_STEPS))
countdown_cond(CTR_I)
G.block("cuairt")
assign_from_table(CU, CU_T, U_STEPS, CTR_I)
assign_from_table(SU, SU_T, U_STEPS, CTR_I)

comment("Lùb V — V_STEPS ceuma gach buice.")
reset_slot(CTR_J, float(V_STEPS))
countdown_cond(CTR_J)
G.block("cuairt")
assign_from_table(CV, CV_T, V_STEPS, CTR_J)
assign_from_table(SV, SV_T, V_STEPS, CTR_J)
vertex()
decrement(CTR_J)
countdown_cond(CTR_J)
G.block("criòch")
G.model_pop()

decrement(CTR_I)
countdown_cond(CTR_I)
G.block("criòch")
G.model_pop()

comment("Sgaoil — deireadh an fhrèim.")
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


MIN_DIST = float("inf")


def render_all():
    """Python mirror of the emitted program: exact same value order, used
    to assert no rounding ties, no %g exponent forms and dist > 1e-5
    anywhere in the animation."""
    global MIN_DIST
    out = []
    az = 0.0
    la = 0.0
    for f in range(FRAMES):
        la = la + LA_STEP
        lx = math.cos(la) * 4.5
        ly = math.sin(la) * 4.5
        lz = math.sin(la * 0.7) * 2.5
        caz = math.cos(az)
        saz = math.sin(az)
        out.append("F")
        for i in range(U_STEPS):
            cu = math.cos(i * U_STEP)
            su = math.sin(i * U_STEP)
            for j in range(V_STEPS):
                cv = math.cos(j * V_STEP)
                sv = math.sin(j * V_STEP)
                rad = 2.0 + 0.8 * cv
                bx = rad * cu
                by = rad * su
                bz = 0.8 * sv
                nx = cv * cu
                ny = cv * su
                y1 = by * CAX - bz * SAX
                z1 = by * SAX + bz * CAX
                x2 = bx * CAX + z1 * SAX
                z2 = z1 * CAX - bx * SAX
                rx = x2 * caz - y1 * saz
                ry = x2 * saz + y1 * caz
                y1n = ny * CAX - sv * SAX
                z1n = ny * SAX + sv * CAX
                x2n = nx * CAX + z1n * SAX
                z2n = z1n * CAX - nx * SAX
                rnx = x2n * caz - y1n * saz
                rny = x2n * saz + y1n * caz
                dx = lx - rx
                dy = ly - ry
                dz = lz - z2
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                MIN_DIST = min(MIN_DIST, dist)
                ndx = dx / dist
                ndy = dy / dist
                ndz = dz / dist
                inten = (rnx * ndx + rny * ndy) + z2n * ndz
                if inten < 0.08:
                    inten = 0.08
                inten = inten / (1.0 + 0.04 * dist)
                w = z2 + 5.0
                px = (rx / w) * 500.0 + 400.0
                py = (ry / w) * 500.0 + 300.0
                for v in (px, py, w, inten):
                    tie_check(v)
                    out.append(g6(v))
        out.append("S")
        az = az + AZ_STEP
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


lines = render_all()
assert MIN_DIST > 1e-5, "dist precondition for normalisation: %r" % MIN_DIST
print("self-check: rendered {} stream lines over {} frames, no rounding "
      "ties, min dist {:g}".format(len(lines), FRAMES, MIN_DIST))
print("peak modelled stack depth: {}".format(max(
    PEAK[0], NSLOTS + 31)))
