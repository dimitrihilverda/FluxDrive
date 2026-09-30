"""S-expressions as KiCad writes them. Quoted strings stay Q (so they are written back quoted)."""
import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


class Q(str):
    """A quoted atom."""


def parse(text):
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(Q(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(a, float):
        return f"{a:.4f}".rstrip("0").rstrip(".") if a != int(a) else str(int(a))
    return str(a)


def dump(node, depth=0):
    """KiCad style: one child list per line, tab-indented; short atom lists stay on one line."""
    if not isinstance(node, list):
        return _atom(node)
    atoms = [x for x in node if not isinstance(x, list)]
    kids = [x for x in node if isinstance(x, list)]
    head = "(" + " ".join(_atom(a) for a in atoms)
    if not kids:
        return head + ")"
    inner = "\n".join("\t" * (depth + 1) + dump(k, depth + 1) for k in kids)
    return head + "\n" + inner + "\n" + "\t" * depth + ")"


def child(node, name):
    return next((c for c in node[1:] if isinstance(c, list) and c and c[0] == name), None)


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]
