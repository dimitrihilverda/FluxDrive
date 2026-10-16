"""Gate-level model of FluxDrive's logic, evaluated on the exported netlist (rev B spec §10.1).

Every net settles to 0, 1 or None (no logic level) from its drivers; the strongest driver wins:
  4    a rail (+3V3, +5V_A, +5V_IN, +5V_DRIVE, +12V, V5SYS -> 1; GND -> 0), and every net a bridged jumper
       joins to it
  3    STRONG: a push-pull gate output, a flip-flop Q, or an external push-pull source (a GPIO that drives)
  2    OD: an open-drain output that pulls low, an external open-collector source (the Amiga's CIA, Gary, a drive),
       or the far side of a resistor of at most 1 kOhm whose near side is at OD or stronger
  1    PULL: a resistor to a rail, or a resistor of more than 1 kOhm to a net at OD or stronger
  0.5  WEAK: an ESP32 internal pull-up (about 45 kOhm)
Drivers of the same top strength with different values: above PULL they are a Conflict; at PULL or below the net has
no logic level (None), as a divider between two rails has (AMIGA_PWR, EFUSE_EN, BUCK_FB). A resistor passes on only
what drives its far net apart from that resistor itself, so a net never holds its own level by its own echo through a
series resistor (a released open-drain output does not keep its bus low). Capacitors and diodes are open (the settled
state). Parts marked DNP are left out unless their ref is in `fit`.
A live gate with an input of no level may drive its output either way, so its output gets no level at the gate's own
strength (STRONG, or OD for an open-drain gate): a floating input shows downstream as None instead of reading as a
released output or as the output's pull (Task 9 review RBUS-8).
A Conflict is raised only if it is still there once the nets have settled: while the nets are settling, a net two
drivers disagree on has no level for the gates and resistors it feeds, and the next round may resolve it.
A name the netlist does not have (a source net, a bridged, fit or state ref) raises KeyError, so a misspelled name
cannot make a check pass for nothing.
"""
from collections import defaultdict

from tools.netlist import parse_ohms

STRONG, OD, PULL, WEAK = 3, 2, 1, 0.5
RAIL = {"+3V3": 1, "+5V_A": 1, "+5V_IN": 1, "+5V_DRIVE": 1, "+12V": 1, "V5SYS": 1, "GND": 0}
# value -> [(kind, input pins, output pin)]; mux inputs are (S, I0, I1)
GATES = {
    "74LVC14A": [("inv", ("1",), "2"), ("inv", ("3",), "4"), ("inv", ("5",), "6"), ("inv", ("9",), "8"),
                 ("inv", ("11",), "10"), ("inv", ("13",), "12")],
    "74LVC07A": [("odbuf", ("1",), "2"), ("odbuf", ("3",), "4"), ("odbuf", ("5",), "6"), ("odbuf", ("9",), "8"),
                 ("odbuf", ("11",), "10"), ("odbuf", ("13",), "12")],
    "SN74LVC2G07": [("odbuf", ("1",), "6"), ("odbuf", ("3",), "4")],
    "74LVC32A": [("or", ("1", "2"), "3"), ("or", ("4", "5"), "6"), ("or", ("9", "10"), "8"),
                 ("or", ("12", "13"), "11")],
    "74LVC1G157": [("mux", ("6", "3", "1"), "4")],
    "SN74LVC2G06": [("odinv", ("1",), "6"), ("odinv", ("3",), "4")],
    "SN74LVC1G06": [("odinv", ("2",), "4")],
    "SN74LVC1G38": [("odnand", ("1", "2"), "4")],
}
# value -> [(name, CLR pin, PRE pin or None, D pin, CLK pin, Q pin)]
FLIPFLOPS = {"74LVC74A": [("A", "1", "4", "2", "3", "5"), ("B", "13", "10", "12", "11", "9")],
             "SN74LVC1G175": [("A", "6", None, "3", "1", "4")]}


class Conflict(Exception):
    pass


class NoFixedPoint(Exception):
    pass


def pin_map(nl):
    """{ref: {pin: net}} of the netlist."""
    out = defaultdict(dict)
    for net, nodes in nl.nets.items():
        for ref, pin, _ in nodes:
            out[ref][pin] = net
    return out


def _live(nl, ref, fit):
    return nl.fitted(ref) or ref in fit


def evaluate(nl, sources, state=None, bridged=None, fit=(), max_iter=80):
    """{net: 0, 1 or None} after settling. sources: {net: (value, strength)}; state: {(ref, "A"/"B"): q} for the
    flip-flops (missing = 0); bridged: {ref: [(pin, pin), ...]} for jumpers and switch pads that are joined — every
    footprint whose value or footprint names "Bridged12" is joined on pins 1-2 unless its ref is given here.
    Raises KeyError for a source net not in nl.nets, for a bridged, fit or state ref not in nl.components, and for a
    pin in a bridged pair that the part does not have (an unconnected pad is in the netlist, so a missing pin is a pad
    number that does not exist);
    Conflict if two drivers still disagree at the fixed point; NoFixedPoint if the nets do not settle."""
    state = state or {}
    for n in sources:
        if n not in nl.nets:
            raise KeyError(f"source net {n!r} is not in the netlist")
    for what, refs in (("bridged", bridged or {}), ("fit", fit), ("state", [k[0] for k in state])):
        for ref in refs:
            if ref not in nl.components:
                raise KeyError(f"{what} ref {ref!r} is not in the netlist")
    pins = pin_map(nl)
    for ref, pairs in (bridged or {}).items():
        for pair in pairs:
            for pin in pair:
                if pin not in pins.get(ref, {}):
                    raise KeyError(f"bridged pin {pin!r} is not on {ref}")
    parent = {n: n for n in nl.nets}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    joins = dict(bridged or {})
    for ref, comp in nl.components.items():
        if ref not in joins and "Bridged12" in comp["value"] + comp["footprint"]:
            joins[ref] = [("1", "2")]
    for ref, pairs in joins.items():
        for a, b in pairs:
            na, nb = pins[ref].get(a), pins[ref].get(b)
            if na and nb:
                parent[find(na)] = find(nb)
    resistors = []
    for ref, comp in nl.components.items():
        if ref.startswith("R") and ref[1:].isdigit() and _live(nl, ref, fit):
            a, b = pins[ref].get("1"), pins[ref].get("2")
            if a and b:
                resistors.append((find(a), find(b), a, b, parse_ohms(comp["value"])))
    logic = [(ref, comp["value"], pins[ref]) for ref, comp in nl.components.items()   # the live gates, once
             if _live(nl, ref, fit) and (comp["value"] in GATES or comp["value"] in FLIPFLOPS)]
    val = {find(n): None for n in nl.nets}
    stren = {k: 0 for k in val}
    prev = {}

    def settle(cands):
        """(value, strength): the strongest candidates win; different values at PULL or weaker are an analog level
        (a divider such as AMIGA_PWR), None; different values above PULL are "X", a Conflict."""
        if not cands:
            return None, 0
        top = max(c[0] for c in cands)
        vals = {c[1] for c in cands if c[0] == top}
        if None in vals:                                    # a strongest driver of no level: the net has none
            return None, top
        if len(vals) > 1:
            return (None, 0) if top <= PULL else ("X", top)
        return vals.pop(), top

    for _ in range(max_iter):
        drv = defaultdict(list)                     # net -> [(strength, value, resistor index or -1)]
        for n in nl.nets:
            if n in RAIL:
                drv[find(n)].append((4, RAIL[n], -1))
        for n, (v, s) in sources.items():
            drv[find(n)].append((s, v, -1))
        for i, (ra, rb, a, b, ohms) in enumerate(resistors):
            for x, y, yn in ((ra, rb, b), (rb, ra, a)):
                if yn in RAIL:
                    drv[x].append((PULL, RAIL[yn], i))
                    continue
                # what drives y apart from this resistor: a net never pulls itself up by its own echo
                vy, sy = settle([c for c in prev.get(y, []) if c[2] != i])
                if vy is None or vy == "X":
                    continue
                if ohms <= 1000:
                    if min(sy, OD) >= PULL:
                        drv[x].append((min(sy, OD), vy, i))
                elif sy >= OD:
                    drv[x].append((PULL, vy, i))
        for ref, value, p in logic:
            for kind, ins, out in GATES.get(value, []):
                if out not in p:
                    continue
                iv = [val[find(p[i])] if i in p else None for i in ins]
                o = find(p[out])
                if None in iv or "X" in iv:                 # it may drive either way: its output has no level
                    drv[o].append((OD if kind.startswith("od") else STRONG, None, -1))
                elif kind == "inv":
                    drv[o].append((STRONG, 1 - iv[0], -1))
                elif kind == "or":
                    drv[o].append((STRONG, iv[0] | iv[1], -1))
                elif kind == "mux":
                    drv[o].append((STRONG, iv[2] if iv[0] else iv[1], -1))
                elif kind == "odbuf" and iv[0] == 0:
                    drv[o].append((OD, 0, -1))
                elif kind == "odinv" and iv[0] == 1:
                    drv[o].append((OD, 0, -1))
                elif kind == "odnand" and iv[0] == 1 and iv[1] == 1:
                    drv[o].append((OD, 0, -1))
            for name, clr, pre, d, clk, q in FLIPFLOPS.get(value, []):
                if q not in p:
                    continue
                c = val[find(p[clr])] if clr in p else 1
                s = val[find(p[pre])] if pre and pre in p else 1
                if c in (None, "X") or s in (None, "X"):
                    continue
                qv = 1 if s == 0 else (0 if c == 0 else state.get((ref, name), 0))
                drv[find(p[q])].append((STRONG, qv, -1))
        new, news = {}, {}
        for k in val:
            new[k], news[k] = settle(drv.get(k, []))
        drv = {k: sorted(v, key=lambda c: (c[0], c[1] is None, c[1] or 0, c[2])) for k, v in drv.items()}
        if new == val and news == stren and drv == prev:
            for k in val:
                if val[k] == "X":
                    raise Conflict((k, sorted((c[0], c[1]) for c in drv[k])))
            return {n: val[find(n)] for n in nl.nets}
        val, stren, prev = new, news, drv
    raise NoFixedPoint(sorted(k for k in val if val[k] is None)[:10])
