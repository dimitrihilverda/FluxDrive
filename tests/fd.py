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
