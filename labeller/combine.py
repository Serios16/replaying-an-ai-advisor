#!/usr/bin/env python3
"""Combining order for the call label, applied to one labeller output.

The labeller lists items; this code turns the list into one label per cut-off.

  python3 combine.py selftest
  python3 combine.py label OUTPUT.json
  python3 combine.py calibrate calibration_set.json [PASS_OUTPUTS.json ...]
  python3 combine.py calibrate heldout_set.json [PASS_OUTPUTS.json ...]

PASS_OUTPUTS.json maps reply id -> labeller output, one file per labelling pass.

Labels: BUY NOW, SELL NOW, LEAN IN, PULL BACK, NO CHANGE, NO PREFERENCE, UNCLEAR.
Cut-offs: strict = proposed or directive items count; loose = floated count too.
"""
import itertools
import json
import re
import sys

STRENGTH = {"floated": 0, "proposed": 1, "directive": 2}
CUTOFF = {"strict": 1, "loose": 0}


def _norm(item):
    """Lower/upper-case enums (the API may vary capitalisation) and fold
    act-at-price buys and sells into resting orders."""
    it = dict(item)
    it["effect"] = str(it["effect"]).upper()
    for key in ("object", "strength", "timing", "condition"):
        it[key] = str(it[key]).lower()
    if it["condition"] == "act_at_price":
        # A buy or sell to carry out when a price is hit counts as an order there.
        if it["effect"] == "BUY_NOW":
            it["effect"] = "LEAN_IN"
        elif it["effect"] == "SELL_NOW":
            it["effect"] = "PULL_BACK"
        if it["effect"] in ("LEAN_IN", "PULL_BACK"):
            it["object"] = "order"
    return it


def _eligible(it):
    """Deferred items and conditionals other than act-at-price are never scored."""
    return it["timing"] == "now" and it["condition"] in ("none", "act_at_price")


def _resolve(items, first, second):
    """Pick a direction within one tier. Opposing directions go to the larger
    share of capital; a tie or a missing size is UNCLEAR.
    Returns (label, tie_break) with tie_break None, 'resolved' or 'unresolved'."""
    a = [it for it in items if it["effect"] == first]
    b = [it for it in items if it["effect"] == second]
    if a and not b:
        return first, None
    if b and not a:
        return second, None
    sizes = [it.get("size_pct") for it in a + b]
    if any(s is None for s in sizes):
        return "UNCLEAR", "unresolved"
    sum_a = sum(it["size_pct"] for it in a)
    sum_b = sum(it["size_pct"] for it in b)
    if abs(sum_a - sum_b) < 1e-9:
        return "UNCLEAR", "unresolved"
    return (first if sum_a > sum_b else second), "resolved"


def label_of(items):
    """Label for a set of items that all count. Returns (label, tier, tie_break)."""
    tier1 = [it for it in items if it["effect"] in ("BUY_NOW", "SELL_NOW")]
    moves = [it for it in items if it["effect"] in ("LEAN_IN", "PULL_BACK")]
    tier2 = [it for it in moves if it["object"] != "plan"]   # orders and reserve
    tier3 = [it for it in moves if it["object"] == "plan"]   # plan-only changes
    for tier, name, pair in ((tier1, "execution", ("BUY_NOW", "SELL_NOW")),
                             (tier2, "order", ("LEAN_IN", "PULL_BACK")),
                             (tier3, "plan-only", ("LEAN_IN", "PULL_BACK"))):
        if tier:
            label, tie = _resolve(tier, *pair)
            return label.replace("_", " "), name, tie
    return "NO CHANGE", None, None


def _result(label, tier=None, tie=None, open_groups=(), note=False):
    """unclear_reason says why a label is UNCLEAR: 'note' (the labeller could not
    determine a recommendation's effect) or 'tie-break' (opposing directions with
    a missing or equal size). tie_break reports whether the larger-share rule ran."""
    reason = None
    if label == "UNCLEAR":
        reason = "note" if note else "tie-break"
    return {"label": label, "tier": tier, "tie_break": tie,
            "unclear_reason": reason, "open_groups": list(open_groups)}


def combine(output, cutoff):
    """Return the label for one labeller output, with the fields of _result()."""
    if output.get("unclear_note"):
        # The effect of some recommendation is unknown, so it could sit in any
        # tier and point either way: no label from the other items is safe.
        return _result("UNCLEAR", note=True)
    floor = CUTOFF[cutoff]
    items = [it for it in map(_norm, output.get("items", [])) if _eligible(it)]

    groups = {}
    for it in items:
        if it.get("alt_group") and it.get("alt_option"):
            groups.setdefault(it["alt_group"], {}).setdefault(it["alt_option"], []).append(it)
    # A "set of alternatives" with one alternative is not a choice.
    groups = {g: opts for g, opts in groups.items() if len(opts) >= 2}

    def grouped(it):
        return bool(it.get("alt_group")) and it["alt_group"] in groups and bool(it.get("alt_option"))

    counted = [it for it in items if not grouped(it) and STRENGTH[it["strength"]] >= floor]
    open_groups = []
    for g, opts in sorted(groups.items()):
        favoured = [o for o, its in opts.items()
                    if any(STRENGTH[it["strength"]] >= 1 for it in its)]
        if len(favoured) == 1:
            # The reply chose: only the favoured alternative counts, at either cut-off.
            counted += [it for it in opts[favoured[0]] if STRENGTH[it["strength"]] >= floor]
        else:
            open_groups.append(g)

    if not open_groups:
        return _result(*label_of(counted))

    # The reply left a choice open. If the choice would change the label,
    # the label is NO PREFERENCE; if every alternative gives the same label, use it.
    outcomes = []
    for pick in itertools.product(*[sorted(groups[g].items()) for g in open_groups]):
        scenario = counted + [it for _, its in pick for it in its]
        outcomes.append(label_of(scenario))
    if len({label for label, _, _ in outcomes}) == 1:
        label = outcomes[0][0]
        tiers = {tier for _, tier, _ in outcomes}
        ties = {tie for _, _, tie in outcomes}
        return _result(label, tiers.pop() if len(tiers) == 1 else None,
                       ties.pop() if len(ties) == 1 else None, open_groups)
    return _result("NO PREFERENCE", open_groups=open_groups)


def labels(output):
    return {c: combine(output, c)["label"] for c in ("strict", "loose")}


def has_advice(output):
    """True if the reply recommends anything at all, including 'keep' or 'wait'."""
    return bool(output.get("items"))


def missing_quotes(output, reply_text):
    """Quotes that are not found in the reply (whitespace- and case-insensitive)."""
    squash = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    text = squash(reply_text)
    return [it["quote"] for it in output.get("items", []) if squash(it["quote"]) not in text]


# --------------------------------------------------------------------------- #

def _item(effect, obj="order", strength="directive", timing="now", condition="none",
          size=None, group=None, option=None):
    return {"quote": "", "effect": effect, "object": obj, "strength": strength,
            "timing": timing, "condition": condition, "size_pct": size,
            "size_text": None, "price": None, "alt_group": group, "alt_option": option}


def _out(*items, note=None):
    return {"items": list(items), "review_triggers": [], "unclear_note": note}


SELFTESTS = [
    ("empty reply", _out(), "NO CHANGE", "NO CHANGE"),
    ("keep only", _out(_item("NO_ACTION")), "NO CHANGE", "NO CHANGE"),
    ("lone floated order change", _out(_item("LEAN_IN", strength="floated")),
     "NO CHANGE", "LEAN IN"),
    ("execution outranks order change",
     _out(_item("PULL_BACK", size=20), _item("BUY_NOW", "market", size=5)),
     "BUY NOW", "BUY NOW"),
    ("order outranks opposite plan-only change",
     _out(_item("PULL_BACK", "order"), _item("LEAN_IN", "plan")), "PULL BACK", "PULL BACK"),
    ("plan-only change alone", _out(_item("PULL_BACK", "plan")), "PULL BACK", "PULL BACK"),
    ("opposing orders, larger share wins",
     _out(_item("LEAN_IN", size=15), _item("PULL_BACK", size=10)), "LEAN IN", "LEAN IN"),
    ("opposing orders, size missing",
     _out(_item("LEAN_IN", size=15), _item("PULL_BACK")), "UNCLEAR", "UNCLEAR"),
    ("opposing orders, equal sizes",
     _out(_item("LEAN_IN", size=10), _item("PULL_BACK", size=10)), "UNCLEAR", "UNCLEAR"),
    ("deferred proposal not scored",
     _out(_item("LEAN_IN", strength="proposed", timing="deferred")), "NO CHANGE", "NO CHANGE"),
    ("conditional cancel not scored",
     _out(_item("PULL_BACK", condition="other")), "NO CHANGE", "NO CHANGE"),
    ("act-at-price buy counts as an order",
     _out(_item("BUY_NOW", "market", condition="act_at_price")), "LEAN IN", "LEAN IN"),
    ("alternatives, wait favoured: passed-over action never counts",
     _out(_item("BUY_NOW", "market", "floated", group="G1", option="A"),
          _item("NO_ACTION", "none", "proposed", group="G1", option="B")),
     "NO CHANGE", "NO CHANGE"),
    ("alternatives, action favoured",
     _out(_item("SELL_NOW", "market", "proposed", group="G1", option="A"),
          _item("NO_ACTION", "order", "floated", group="G1", option="B")),
     "SELL NOW", "SELL NOW"),
    ("alternatives, none favoured",
     _out(_item("BUY_NOW", "market", "floated", group="G1", option="A"),
          _item("NO_ACTION", "none", "floated", group="G1", option="B")),
     "NO PREFERENCE", "NO PREFERENCE"),
    ("open choice that cannot change the label",
     _out(_item("BUY_NOW", "market", size=5),
          _item("LEAN_IN", "order", "floated", group="G1", option="A"),
          _item("NO_ACTION", "order", "floated", group="G1", option="B")),
     "BUY NOW", "BUY NOW"),
    ("two alternatives both favoured is still an open choice",
     _out(_item("LEAN_IN", "order", "proposed", group="G1", option="A"),
          _item("PULL_BACK", "order", "proposed", group="G1", option="B")),
     "NO PREFERENCE", "NO PREFERENCE"),
    ("unclear note", _out(_item("LEAN_IN"), note="cannot record"), "UNCLEAR", "UNCLEAR"),
    ("unclear note beside an execution is still unclear",
     _out(_item("BUY_NOW", "market", size=5), note="cannot record"), "UNCLEAR", "UNCLEAR"),
    ("open choice, same label from different tiers",
     _out(_item("LEAN_IN", "order", "floated", group="G1", option="A"),
          _item("LEAN_IN", "plan", "floated", group="G1", option="B")),
     "LEAN IN", "LEAN IN"),
    ("three options, none favoured",
     _out(_item("BUY_NOW", "market", "floated", size=5, group="G1", option="A"),
          _item("LEAN_IN", "order", "floated", group="G1", option="B"),
          _item("NO_ACTION", "none", "floated", group="G1", option="C")),
     "NO PREFERENCE", "NO PREFERENCE"),
    ("floated opposite order change with a missing size: cut-offs split",
     _out(_item("LEAN_IN", "order", "proposed"), _item("PULL_BACK", "order", "floated", size=10)),
     "LEAN IN", "UNCLEAR"),
    ("capitalisation differs", _out({**_item("LEAN_IN"), "effect": "lean_in",
                                     "strength": "Directive"}), "LEAN IN", "LEAN IN"),
]


def selftest():
    bad = 0
    for name, out, strict, loose in SELFTESTS:
        got = labels(out)
        ok = got == {"strict": strict, "loose": loose}
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")
    print(f"{len(SELFTESTS) - bad}/{len(SELFTESTS)} self-tests pass")
    return bad == 0


def calibrate(set_path, pass_paths):
    cal = json.load(open(set_path, encoding="utf-8"))
    ok = True
    print("Expected outputs vs expected labels (the set must agree with itself):")
    for r in cal["replies"]:
        got = labels(r["expected"])
        same = got == r["expected_labels"]
        ok &= same
        lost = missing_quotes(r["expected"], r["text"])
        ok &= not lost
        print(f"  {r['id']}: {got}{'' if same else '  <-- differs from ' + str(r['expected_labels'])}"
              f"{'  quotes not in text: ' + str(lost) if lost else ''}")
    misses = 0
    for path in pass_paths:
        outputs = json.load(open(path, encoding="utf-8"))
        print(f"Pass {path}:")
        for r in cal["replies"]:
            out = outputs.get(r["id"])
            if out is None:
                print(f"  {r['id']}: no output (failed call: rerun)")
                ok = False
                continue
            got = labels(out)
            miss = got != r["expected_labels"]
            misses += miss
            lost = missing_quotes(out, r["text"])
            print(f"  {r['id']}: {got}{'  MISS, expected ' + str(r['expected_labels']) if miss else ''}"
                  f"{'  [' + str(len(lost)) + ' quote(s) not verbatim]' if lost else ''}")
    if pass_paths:
        limit = cal["pass_rule"]["max_misses"]
        print(f"Misses: {misses} (allowed: {limit}) -> "
              f"{'PASS' if misses <= limit else cal['pass_rule']['verdict_if_exceeded']}")
        ok &= misses <= limit
    return ok


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "selftest":
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) >= 3 and sys.argv[1] == "label":
        out = json.load(open(sys.argv[2], encoding="utf-8"))
        print(json.dumps({c: combine(out, c) for c in ("strict", "loose")}, indent=2))
        sys.exit(0)
    if len(sys.argv) >= 3 and sys.argv[1] == "calibrate":
        sys.exit(0 if calibrate(sys.argv[2], sys.argv[3:]) else 1)
    print(__doc__)
    sys.exit(2)
