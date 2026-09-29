"""Helpers for the FluxDrive netlist tests."""
RAILS = {"+5V_IN", "+5V_A", "V5SYS", "VBUS", "+3V3", "GND"}


def pulls(nl, net):
    """Sorted [(value, rail)] of fitted resistors between `net` and a rail."""
    out = []
    for ref, a, b, _ in nl.resistors():
        if net in (a, b):
            other = b if a == net else a
            if other in RAILS:
                out.append((nl.components[ref]["value"], other))
    return sorted(out)


def between(nl, ref):
    return {nl.net_of(ref, 1), nl.net_of(ref, 2)}


def parts_between(nl, a, b, prefix="R"):
    """Fitted two-pin parts whose pins are on nets a and b."""
    return sorted(r for r, c in nl.components.items()
                  if r.startswith(prefix) and nl.fitted(r) and between(nl, r) == {a, b})


def esp_net(nl, gpio):
    for name in (f"IO{gpio}", {19: "USB_D-", 20: "USB_D+", 43: "TXD0", 44: "RXD0"}.get(gpio, "")):
        if name:
            net = nl.net_of_function("U1", name)
            if net is not None:
                return net
    raise AssertionError(f"U1 has no pin for GPIO{gpio}")


def is_nc(net):
    return net is None or net.startswith("unconnected-")


def dnp_between(nl, a, b, prefix):
    """Unfitted two-pin parts whose pins are on nets a and b."""
    return sorted(r for r in nl.components
                  if r.startswith(prefix) and not nl.fitted(r) and between(nl, r) == {a, b})


def solve(nl, fixed):
    """DC node voltages of the fitted resistors, with `fixed` = {net: volts}. Everything else (diodes, the eFuse,
    IC pins) is open, which is the state with those parts off or reverse-biased."""
    edges = [(a, b, 1.0 / ohms) for _, a, b, ohms in nl.resistors() if ohms and a and b and a != b]
    nets = sorted({n for a, b, _ in edges for n in (a, b) if n not in fixed})
    idx = {n: i for i, n in enumerate(nets)}
    size = len(nets)
    g = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for a, b, c in edges:
        for x, y in ((a, b), (b, a)):
            if x in idx:
                g[idx[x]][idx[x]] += c
                if y in idx:
                    g[idx[x]][idx[y]] -= c
                else:
                    rhs[idx[x]] += c * fixed[y]
    for i in range(size):
        g[i][i] += 1e-12                                  # a floating island settles at 0 V instead of failing
    for i in range(size):                                 # Gaussian elimination with partial pivoting
        p = max(range(i, size), key=lambda k: abs(g[k][i]))
        g[i], g[p], rhs[i], rhs[p] = g[p], g[i], rhs[p], rhs[i]
        for k in range(i + 1, size):
            f = g[k][i] / g[i][i]
            if f:
                for j in range(i, size):
                    g[k][j] -= f * g[i][j]
                rhs[k] -= f * rhs[i]
    v = [0.0] * size
    for i in reversed(range(size)):
        v[i] = (rhs[i] - sum(g[i][j] * v[j] for j in range(i + 1, size))) / g[i][i]
    return {**fixed, **dict(zip(nets, v))}
