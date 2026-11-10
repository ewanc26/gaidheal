#!/usr/bin/env python3
"""Generate examples/donut_engine.gaidheal: a finite animated torus streaming
shaded quads to the SDL2 token-protocol host in host/donut_host.c.

Gàidheal has no trig, no variables, and no strings, so:

- sin/cos come from a 16-sample cosine table baked in at generation time as
  base stack slots; a lookup is an unrolled 16-way `ma`/`no` ladder
  (`chuir`/`gcuir` indices are source literals, so selection cannot loop),
  and the in-between value is linear interpolation with only
  `suim`/`shuim`/`bsuim`/`dealaich`.
- Angles reduce to [0, 2π) with `dhealaich` (remainder) plus one negative
  fix-up; sin(x) = cos(x + 3π/2).
- Loop and vertex state lives in stack slots addressed by `chuir`/`gcuir`;
  every literal access index below is computed by simulating the stack in
  this generator, so the emitted program is index-correct by construction.

Counted loops use the documented `cuairt` discipline: push one condition
value before the loop; the body's final act is to leave the next iteration's
condition on top.

Run:    ./target/release/gaidheal examples/donut_engine.gaidheal | ./host_bin
Headless (the host replays the finite stream forever):
  ... | SDL_VIDEODRIVER=dummy ./host_bin --frames 3
"""

import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

R, TUBE = 3.0, 1.25
RING, TUBE_N = 16, 10          # 160 quads per frame
SCALE, OX, OY = 28.0, 120.0, 120.0
SPIN_STEP = 0.05
TILT = 0.72
LIGHT = (0.32, 0.58, 0.75)
FRAMES = 60
TH_STEP = 2 * math.pi / RING   # ring angle step
PH_STEP = 2 * math.pi / TUBE_N  # tube angle step
CB, SB = round(math.cos(TILT), 12), round(math.sin(TILT), 12)

TN = 32                         # cosine table samples over [0, 2π)
TTH = 2 * math.pi / TN          # table step
TP = 2 * math.pi
H3P2 = 3 * math.pi / 2          # sin(x) = cos(x + 3π/2)
TABLE = [round(math.cos(k * TTH), 12) for k in range(TN)]


def num(v):
    return repr(round(v, 12))


class Gh:
    """Emitter with a symbolic stack model: every emitted operation updates
    the model, so `chuir`/`gcuir` literal indices are always correct."""

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
        at runtime, so the model must pop it too (the body runs with that
        value already consumed)."""
        self.out.append(word)
        if word in ("cuairt", "ma", "mha"):
            self.stack.pop()

    def model_pop(self):
        """Account for a value the machine consumes at runtime but that has
        no source word here (the `cuairt` re-test pops the trailing loop
        condition)."""
        self.stack.pop()

    def newslot(self, initial=0.0):
        self.push(initial)
        return len(self.stack) - 1               # absolute position

    def setslot(self, pos):
        """Store the value on top into slot pos IN PLACE — the old value must
        not be on top. Gàidheal has no in-place store, so: roll the old slot
        value up (gcuir) and drop it, then restore the shifted region by
        lifting each displaced element back to the top (repeated gcuir with
        the constant depth of the region's bottom). Net effect: [S, X, R,
        new] -> [S, new, R]. Without this the region above the slot would
        shift and every later fixed chuir/gcuir index in a loop body would
        be wrong on the second iteration."""
        n = len(self.stack)
        self.roll(pos)                  # gcuir: old slot value to top
        self.emit("leig")               # drop the old value
        for _ in range(n - 2 - pos):    # each lift: gcuir with constant idx
            self.roll(pos)              # (idx = n-2-pos; region bottom rises)


G = Gh()


def comment(text):
    G.out.append("( " + text + " )")


def emit_str(s):
    """Emit a literal token plus the newline separator (code point 10)."""
    for ch in s + "\n":
        G.push(ord(ch))
        G.emit("n-abair")


def print_top():
    G.emit("abair")


# ------------------------------------------------------------ cosine table
comment("Bòrd co-shìnte: 16 sampall de cos eadar 0 agus 2π.")
for v in TABLE:
    G.push(v)
TPOS = [len(G.stack) - TN + k for k in range(TN)]    # absolute positions


def table_val(k):
    """Push cosine table sample k (k == TN wraps to T[0])."""
    if k == TN:
        G.push(TABLE[0])
    else:
        G.copy(TPOS[k])


def cos_top():
    """Consume the angle on top, push cos(angle)."""
    # r = x mod 2π, then +2π if negative
    G.push(TP)
    G.emit("dhealaich")             # a = x, b = 2π → r0
    G.emit("tog")                   # [r0, r0]
    G.push(0.0)
    G.emit("coimeas")              # r0 < 0 ?
    G.block("ma")
    G.push(TP)
    G.emit("suim")                 # r0 + 2π
    G.block("criòch")
    # top: r ∈ [0, 2π)

    def seg(k):
        # v = T(k) + frac·(T(k+1) − T(k)), frac = (r − k·TTH)/TTH
        G.emit("tog")                 # [r, r] — keep the angle for the drop
        G.push(k * TTH)
        G.emit("shuim")             # r − k·TTH
        G.push(TTH)
        G.emit("dealaich")          # frac
        table_val(k + 1)            # [frac, T(k+1)]
        table_val(k)                # [frac, T(k+1), T(k)]
        G.emit("shuim")             # T(k+1) − T(k)
        G.emit("malairt")           # [frac, T(k+1)−T(k)]→[d, frac]
        G.emit("bsuim")             # frac·d
        table_val(k)                # [t, T(k)]
        G.emit("suim")              # v
        G.emit("lheig")             # drop the angle (2nd from top)

    def ladder(k):
        if k == TN - 1:
            seg(k)                  # last segment runs unconditionally
            return
        G.emit("tog")               # [r, r]
        G.push((k + 1) * TTH)
        G.emit("coimeas")          # r < (k+1)·TTH ?
        G.block("ma")
        seg(k)
        G.block("no")
        ladder(k + 1)
        G.block("criòch")

    ladder(0)


def assign_cos_from(dest, source, offset=0.0):
    """dest := cos(source + offset)."""
    G.copy(source)
    if offset:
        G.push(offset)
        G.emit("suim")
    cos_top()
    G.setslot(dest)


def assign_sin_from(dest, source, offset=0.0):
    """dest := sin(source + offset)."""
    G.copy(source)
    if offset:
        G.push(offset)
        G.emit("suim")
    G.push(H3P2)
    G.emit("suim")
    cos_top()
    G.setslot(dest)


# ------------------------------------------------------------------- slots
comment("Seadaichean-obrach: trighirimhean, ceumannan, agus cunntadairean.")
CA = G.newslot()
SA = G.newslot()
CT1 = G.newslot()
ST1 = G.newslot()
CT2 = G.newslot()
ST2 = G.newslot()
CP1 = G.newslot()
SP1 = G.newslot()
CP2 = G.newslot()
SP2 = G.newslot()
ANG_I = G.newslot()                    # ring angle θ
ANG_J = G.newslot()                    # tube angle φ
CTR_I = G.newslot(float(RING))
CTR_J = G.newslot(float(TUBE_N))
CTR_F = G.newslot(float(FRAMES))
A = G.newslot(0.0)                     # spin angle


def reset_slot(pos, value):
    """Store a constant into a slot (re-initialise loop counters)."""
    G.push(value)
    G.setslot(pos)


def countdown_cond(pos):
    """Push 1 if slot pos > 0 else 0 — a `cuairt` condition."""
    G.copy(pos)
    G.push(0.0)
    G.emit("choimeas")             # n > 0


def decrement(pos):
    G.copy(pos)
    G.push(1.0)
    G.emit("shuim")
    G.setslot(pos)


# ----------------------------------------------------------------- helpers
def corner(cp, sp, ct, stt):
    """Print the two screen coords of one quad corner (slot addresses)."""
    G.copy(cp)
    G.push(TUBE)
    G.emit("bsuim")
    G.push(R)
    G.emit("suim")                      # rad = cosφ·TUBE + R
    G.emit("tog")
    G.copy(ct)
    G.emit("bsuim")                     # x = rad·cosθ
    G.copy(sp)
    G.push(TUBE)
    G.emit("bsuim")                     # y = sinφ·TUBE
    rad_pos = len(G.stack) - 3
    G.copy(rad_pos)
    G.copy(stt)
    G.emit("bsuim")                     # z = rad·sinθ
    x_pos = len(G.stack) - 3
    y_pos = len(G.stack) - 2
    z_pos = len(G.stack) - 1
    # cy = y·ca − z·sa
    G.copy(y_pos)
    G.copy(CA)
    G.emit("bsuim")
    G.copy(z_pos)
    G.copy(SA)
    G.emit("bsuim")
    G.emit("shuim")                      # cy
    cy_pos = len(G.stack) - 1
    # cz = y·sa + z·ca
    G.copy(y_pos)
    G.copy(SA)
    G.emit("bsuim")
    G.copy(z_pos)
    G.copy(CA)
    G.emit("bsuim")
    G.emit("suim")                       # cz
    cz_pos = len(G.stack) - 1
    # px = OX + (x·CB + cz·SB)·SCALE
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
    print_top()
    # py = OY − cy·SCALE
    G.push(OY)
    G.copy(cy_pos)
    G.push(SCALE)
    G.emit("bsuim")
    G.emit("shuim")                       # py
    print_top()
    for _ in range(6):                    # rad, x, y, z, cy, cz
        G.emit("leig")


def quad(cp1, sp1, ct1, stt1, cp2, sp2, ct2, stt2):
    """Print normals-driven colours, then 'P', 4 corners, 3 colour values."""
    base_depth = len(G.stack)
    # ny = sp1·ca − cp1·st1·sa
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
    # nz = sp1·sa + cp1·st1·ca
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
    # nx = cp1·ct1·CB + nz·SB
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
    # lum = (nx·Lr + ny·Lg + nz·Lb + 1)·0.5
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
    # three colour values stay on the stack until after the coordinates
    lum_pos = len(G.stack) - 1               # lum is on top here
    for mul, add in ((150.0, 80.0), (90.0, 50.0), (60.0, 30.0)):
        G.copy(lum_pos)
        G.push(mul)
        G.emit("bsuim")
        G.push(add)
        G.emit("suim")                       # r / g / b
    # drop the four normals: positions from the bottom up (nothing above
    # them moves), rolling each to the top to drop it in place
    while len(G.stack) > base_depth + 3:
        pos = len(G.stack) - 4
        G.roll(pos)
        G.emit("leig")
    emit_str("P")
    for cp, sp, ct, stt in ((cp1, sp1, ct1, stt1),
                            (cp2, sp1, ct1, stt1),
                            (cp2, sp1, ct2, stt2),
                            (cp1, sp1, ct2, stt2)):
        corner(cp, sp, ct, stt)
    # now print r, g, b (b is on top)
    r_pos = len(G.stack) - 3
    g_pos = len(G.stack) - 2
    G.copy(r_pos)
    print_top()                              # r
    G.copy(g_pos)
    print_top()                              # g
    print_top()                              # b (pops it)
    G.emit("leig")                           # drop r
    G.emit("leig")                           # drop g



# -------------------------------------------------------------------- main
comment("An t-einnsean donut: toirgeoill bheò do dhonut_host SDL2")
comment("le cos/sin à bòrd co-shìnte — gun trig, le + − × ÷ a-mhàin.")
comment("Air a ghintinn le scripts/gen_donut_engine.py — FRAMES 60.")

countdown_cond(CTR_F)
G.block("cuairt")
comment("Fhràmadh: A += SPIN_STEP; ca/sa à A; sgaoil F.")

G.copy(A)
G.push(SPIN_STEP)
G.emit("suim")
G.setslot(A)
assign_cos_from(CA, A)
assign_sin_from(SA, A)
emit_str("F")

comment("Ath-shuidhic ni airson gach fràma.")
reset_slot(CTR_I, float(RING))

comment("Ceallaichean a' chrò:",)
comment("teta = TH_STEP air i; tha ni ag dol sios.")
countdown_cond(CTR_I)
G.block("cuairt")
G.push(RING)
G.copy(CTR_I)
G.emit("shuim")                          # RING − ni (counter counts down)
G.push(TH_STEP)
G.emit("bsuim")
G.setslot(ANG_I)                          # θ
assign_cos_from(CT1, ANG_I)
assign_sin_from(ST1, ANG_I)
assign_cos_from(CT2, ANG_I, offset=TH_STEP)
assign_sin_from(ST2, ANG_I, offset=TH_STEP)

comment("Ath-shuidhic nj airson gach cealla den chrò.")
reset_slot(CTR_J, float(TUBE_N))

comment("Ceallaichean a' phiob:",)
comment("fi = PH_STEP air j; tha nj ag dol sios.")
countdown_cond(CTR_J)
G.block("cuairt")
G.push(TUBE_N)
G.copy(CTR_J)
G.emit("shuim")
G.push(PH_STEP)
G.emit("bsuim")
G.setslot(ANG_J)                          # φ
assign_cos_from(CP1, ANG_J)
assign_sin_from(SP1, ANG_J)
assign_cos_from(CP2, ANG_J, offset=PH_STEP)
assign_sin_from(SP2, ANG_J, offset=PH_STEP)

comment("Ceithir-cheàrnach le sgàilean: P, ceithir cheàrn, tri dathan.")
quad(CP1, SP1, CT1, ST1, CP2, SP2, CT2, ST2)

decrement(CTR_J)
countdown_cond(CTR_J)
G.block("criòch")
G.model_pop()

decrement(CTR_I)
countdown_cond(CTR_I)
G.block("criòch")
G.model_pop()

comment("Slànaich am frèam.")
emit_str("S")
decrement(CTR_F)
countdown_cond(CTR_F)
G.block("criòch")
G.model_pop()

comment("Crìoch an t-srutha.")

text = "\n".join(G.out) + "\n"
assert len(G.stack) == TN + 16, "unbalanced model stack: %d" % len(G.stack)
(ROOT / "examples" / "donut_engine.gaidheal").write_text(text, encoding="utf-8")
print("wrote examples/donut_engine.gaidheal: {} lines".format(len(text.splitlines())))
