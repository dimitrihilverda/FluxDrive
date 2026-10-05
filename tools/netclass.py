"""Track widths from a KiCad 10 project's netclasses (LCODE-8). No pcbnew, so the tests can import it."""
import fnmatch
import json
import pathlib


def netclass_widths(pro_path):
    """({class: track width mm}, [(net pattern, class)]) from a KiCad 10 project file."""
    ns = json.loads(pathlib.Path(pro_path).read_text(encoding="utf-8"))["net_settings"]
    widths = {c["name"]: c["track_width"] for c in ns["classes"]}
    return widths, [(p["pattern"], p["netclass"]) for p in ns.get("netclass_patterns", [])]


def width_of(net, widths, patterns):
    """The track width of `net`: the class of its first matching pattern, else Default."""
    for pat, cls in patterns:
        if fnmatch.fnmatchcase(net, pat):
            return widths.get(cls, widths["Default"])
    return widths["Default"]
