"""Read a KiCad netlist (kicadsexpr format) into plain Python dicts.

Export with:  bash tools/export_netlist.sh  (writes build/FluxDrive.net)
Copied from the Nano-Tek (2623d2f), plus DNP awareness.
"""
from dataclasses import dataclass, field
import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def _parse_sexpr(text):
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\"', '"'))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _child(node, name):
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return None


def _children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def _value(node, name, default=None):
    c = _child(node, name)
    return c[1] if c is not None and len(c) > 1 else default


@dataclass
class Netlist:
    components: dict = field(default_factory=dict)   # ref -> {"value", "footprint", "fields"}
    nets: dict = field(default_factory=dict)         # net name -> [(ref, pin, pinfunction)]

    def net_of(self, ref, pin):
        for name, nodes in self.nets.items():
            if any(r == ref and p == str(pin) for r, p, _ in nodes):
                return name
        return None

    def net_of_function(self, ref, function):
        for name, nodes in self.nets.items():
            if any(r == ref and f == function for r, _, f in nodes):
                return name
        return None

    def refs_on(self, net):
        return sorted({r for r, _, _ in self.nets.get(net, [])})

    def fitted(self, ref):
        """False for parts marked DNP in the schematic (their footprint stays, JLC fits nothing)."""
        f = self.components[ref]["fields"]
        return "dnp" not in f and f.get("DNP", "") not in ("1", "yes")

    def resistors(self):
        """[(ref, net_a, net_b, ohms)] for every fitted two-pin R* component."""
        out = []
        for ref, comp in self.components.items():
            if not re.fullmatch(r"R\d+", ref) or not self.fitted(ref):
                continue
            a, b = self.net_of(ref, 1), self.net_of(ref, 2)
            try:
                ohms = parse_ohms(comp["value"])
            except ValueError:
                ohms = None                  # unvalued "R": the sim ignores it, the tests see the value
            out.append((ref, a, b, ohms))
        return out


def parse_ohms(value):
    """'4K7' -> 4700, '100K' -> 100000, '330' -> 330, '22' -> 22, '1M' -> 1e6."""
    v = value.strip().upper().replace("Ω", "").replace("OHM", "")
    m = re.fullmatch(r"(\d+)([RKM])(\d*)", v)
    if m:
        mult = {"R": 1, "K": 1e3, "M": 1e6}[m.group(2)]
        return float(f"{m.group(1)}.{m.group(3) or 0}") * mult
    return float(v)


def load(path):
    with open(path, encoding="utf-8") as f:
        root = _parse_sexpr(f.read())
    nl = Netlist()
    for comp in _children(_child(root, "components"), "comp"):
        fields = {}
        fl = _child(comp, "fields")
        if fl is not None:
            for fld in _children(fl, "field"):
                name = _value(fld, "name")
                fields[name] = fld[-1] if isinstance(fld[-1], str) else ""
        for prop in _children(comp, "property"):
            fields[_value(prop, "name")] = _value(prop, "value", "")
        nl.components[_value(comp, "ref")] = {
            "value": _value(comp, "value", ""),
            "footprint": _value(comp, "footprint", ""),
            "fields": fields,
        }
    for net in _children(_child(root, "nets"), "net"):
        nodes = []
        for n in _children(net, "node"):
            pin, func = _value(n, "pin"), _value(n, "pinfunction", "")
            if func.endswith("_" + pin):          # KiCad 10 writes "DP1_A6"; KiCad 9 wrote "DP1"
                func = func[: -(len(pin) + 1)]
            nodes.append((_value(n, "ref"), pin, func))
        nl.nets[_value(net, "name").lstrip("/")] = nodes
    return nl
