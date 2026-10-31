#!/usr/bin/env python3
"""score.py - scoring for the replay-fidelity test (decision 3).

  python3 score.py score MANIFEST.json [--json OUT.json]
  python3 score.py selftest
  python3 score.py example          (prints an invented manifest)

Input is one manifest (see manifest_schema.json) with one row per labelled
reply. The script prints a report and, as its last line, the branch decision.
The branch is the only thing it decides. Everything else is description.

No network, no API calls, standard library only, deterministic.
"""
import hashlib
import json
import math
import random
import sys
from collections import Counter
from datetime import date
from fractions import Fraction as F

# --------------------------------------------------------------------------- #
# Registered numbers (decision 3). Changing any of these changes the checksum.
# --------------------------------------------------------------------------- #
HIGH = F(80, 100)            # score / scoreable weeks at or above this is "high"
LOW = F(50, 100)             # at or below this is "low"
MARGIN = 3                   # weeks by which a high score must beat the bar ...
MARGIN_SHARE = F(30, 100)    # ... and at least this share of the scoreable weeks
MIN_WEEKS = 8                # fewer scoreable weeks: extension, result not read
MIN_SAMPLES = 3              # fewer valid replays in a week: week excluded
AGREE_ALL = F(85, 100)       # two passes, same strict label, whole pool
AGREE_ACTION = F(70, 100)    # same, replies where either pass is not NO CHANGE
DOMINANCE = F(80, 100)       # one label on this share of scoreable originals
MIN_ACTION_POOL = 10         # the action-label minimum is enforced from this many replies
MAX_ATTEMPTS = 3             # a sample is the first try plus at most two resends
STAGES = ("A", "extension")  # extension: all weeks pooled; a second "more weeks" is final
UNSTABLE = F(60, 100)        # top label holds this share of valid replays or less
FIRM = F(80, 100)            # top label holds this share or more
BLOCK = 2                    # consecutive weeks per bootstrap block
RESAMPLES = 10000
SEED = 20261010
PCT_LO, PCT_HI = F(5, 100), F(95, 100)

CUTOFFS = ("strict", "loose")
LABELS = ("BUY NOW", "SELL NOW", "LEAN IN", "PULL BACK", "NO CHANGE",
          "NO PREFERENCE", "UNCLEAR")
SHORT = {"BUY NOW": "BN", "SELL NOW": "SN", "LEAN IN": "LI", "PULL BACK": "PB",
         "NO CHANGE": "NC", "NO PREFERENCE": "NP", "UNCLEAR": "UN", "PENDING": "??"}
UNCLEAR, PENDING, NO_CHANGE = "UNCLEAR", "PENDING", "NO CHANGE"
KINDS = ("original", "replay", "interim", "framework", "old9",
         "yardstick_old", "yardstick_new")
HISTORY_KINDS = ("original", "interim", "framework", "old9")  # can be "last advice"
CHECKIN_KINDS = ("original", "old9")                          # numbered check-ins
RULES = ("a", "b", "c")
RULE_NAMES = {"a": "previous numbered check-in",
              "b": "most recent reply with an item",
              "c": "always NO CHANGE"}


class ManifestError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Manifest loading and validation
# --------------------------------------------------------------------------- #

def _label(value, where):
    if not isinstance(value, str):
        raise ManifestError(f"{where}: label must be a string")
    lab = value.strip().upper().replace("_", " ")
    if lab not in LABELS:
        raise ManifestError(f"{where}: unknown label {value!r}")
    return lab


def _day(value, where):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ManifestError(f"{where}: date must start with YYYY-MM-DD") from None


def _whole(value, low=None, high=None):
    return (isinstance(value, int) and not isinstance(value, bool)
            and (low is None or value >= low) and (high is None or value <= high))


def load(manifest):
    """Validate a manifest dict and return (weeks, rows, samples per week, stage).
    Anything malformed is reported as a ManifestError, never as a crash."""
    try:
        return _load(manifest)
    except ManifestError:
        raise
    except (TypeError, KeyError, AttributeError, ValueError) as err:
        raise ManifestError(f"malformed manifest ({type(err).__name__}: {err})") from None


def _load(manifest):
    if not isinstance(manifest, dict) or "replies" not in manifest or "run" not in manifest:
        raise ManifestError("manifest needs 'run' and 'replies'")
    weeks = manifest["run"].get("weeks")
    if not isinstance(weeks, list) or not weeks or not all(_whole(w) for w in weeks):
        raise ManifestError("run.weeks must be a non-empty list of week numbers")
    if len(set(weeks)) != len(weeks):
        raise ManifestError("run.weeks has a repeated week")
    expected = manifest["run"].get("samples_per_week", 5)
    if not _whole(expected, 1):
        raise ManifestError("run.samples_per_week must be a whole number, 1 or more")
    stage = manifest["run"].get("stage", "A")
    if stage not in STAGES:
        raise ManifestError(f"run.stage must be one of {', '.join(STAGES)}")
    rows, seen = [], set()
    for i, raw in enumerate(manifest["replies"]):
        rid = raw.get("reply_id")
        where = f"reply {rid!r} (row {i})"
        if not isinstance(rid, str) or not rid:
            raise ManifestError(f"row {i}: reply_id missing")
        if rid in seen:
            raise ManifestError(f"{where}: duplicate reply_id")
        seen.add(rid)
        kind = raw.get("kind")
        if kind not in KINDS:
            raise ManifestError(f"{where}: unknown kind {kind!r}")
        chat = raw.get("chat")
        if chat not in ("OLD", "NEW"):
            raise ManifestError(f"{where}: chat must be OLD or NEW")
        status = raw.get("status", "ok")
        if status not in ("ok", "failed"):
            raise ManifestError(f"{where}: status must be ok or failed")
        week, pos, sample, attempts = (raw.get("week"), raw.get("position"),
                                       raw.get("sample"), raw.get("attempts"))
        if kind in ("original", "replay", "old9", "yardstick_old", "yardstick_new"):
            if not _whole(week):
                raise ManifestError(f"{where}: week number required for kind {kind}")
        if kind in HISTORY_KINDS and not _whole(pos):
            raise ManifestError(f"{where}: position required for kind {kind}")
        if kind == "replay":
            if not _whole(sample, 1, expected):
                raise ManifestError(f"{where}: sample must be a number from 1 to {expected}")
            if week not in weeks:
                raise ManifestError(f"{where}: replay for week {week}, which is not in run.weeks")
            if not _whole(attempts, 1, MAX_ATTEMPTS):
                raise ManifestError(f"{where}: attempts must be a number from 1 to {MAX_ATTEMPTS}")
        row = {"reply_id": rid, "kind": kind, "chat": chat, "status": status,
               "week": week, "position": pos, "sample": sample, "attempts": attempts,
               "date": _day(raw.get("date"), where), "passes": []}
        if status == "failed":
            if kind != "replay":
                raise ManifestError(f"{where}: only a replay can have status failed")
            rows.append(row)
            continue
        passes = raw.get("passes")
        if not isinstance(passes, list) or not 2 <= len(passes) <= 3:
            raise ManifestError(f"{where}: needs two passes, or three after a disagreement")
        numbers = [p.get("pass") for p in passes]
        if not all(_whole(x) for x in numbers) or sorted(numbers) != list(range(1, len(passes) + 1)):
            raise ManifestError(f"{where}: passes must be numbered 1, 2 (and 3)")
        for p in sorted(passes, key=lambda p: p["pass"]):
            n_items = p.get("n_items")
            if not _whole(n_items, 0):
                raise ManifestError(f"{where}: pass {p['pass']} needs n_items (0 or more)")
            entry = {"pass": p["pass"], "n_items": n_items}
            for cutoff in CUTOFFS:
                block = p.get(cutoff)
                if not isinstance(block, dict):
                    raise ManifestError(f"{where}: pass {p['pass']} needs a {cutoff} block")
                if block.get("tie_break") not in (None, "resolved", "unresolved"):
                    raise ManifestError(f"{where}: bad tie_break in pass {p['pass']}")
                if block.get("unclear_reason") not in (None, "note", "tie-break"):
                    raise ManifestError(f"{where}: bad unclear_reason in pass {p['pass']}")
                entry[cutoff] = {"label": _label(block.get("label"), where),
                                 "tie_break": block.get("tie_break"),
                                 "unclear_reason": block.get("unclear_reason")}
            row["passes"].append(entry)
        rows.append(row)

    by_week = Counter(r["week"] for r in rows if r["kind"] == "original")
    checkin_weeks = Counter(r["week"] for r in rows if r["kind"] in CHECKIN_KINDS)
    for w, n in checkin_weeks.items():
        if n > 1:
            raise ManifestError(f"week {w}: more than one numbered check-in row")
    for w in weeks:
        if by_week[w] != 1:
            raise ManifestError(f"week {w}: needs exactly one row of kind original, found {by_week[w]}")
        if not checkin_weeks[w - 1]:
            raise ManifestError(f"week {w}: the previous numbered check-in (#{w - 1}) has no row; "
                                "add it so the naive rules have their source")
        have = {r["sample"] for r in rows if r["kind"] == "replay" and r["week"] == w}
        missing = sorted(set(range(1, expected + 1)) - have)
        if missing:
            raise ManifestError(f"week {w}: no replay row for sample(s) {missing}; every sample "
                                "needs a row, with status failed if it stayed invalid")
    positions = Counter((r["chat"], r["position"]) for r in rows if r["kind"] in HISTORY_KINDS)
    for key, n in positions.items():
        if n > 1:
            raise ManifestError(f"chat {key[0]}: position {key[1]} used by more than one reply")
    samples = Counter((r["week"], r["sample"]) for r in rows if r["kind"] == "replay")
    for key, n in samples.items():
        if n > 1:
            raise ManifestError(f"week {key[0]}: sample {key[1]} appears more than once")
    return sorted(weeks), rows, expected, stage


# --------------------------------------------------------------------------- #
# One label per reply
# --------------------------------------------------------------------------- #

def resolve(row, cutoff):
    """Label for a reply at one cut-off, from its passes.

    Two passes agree: that label. They differ: the label two of three passes
    share; if all three differ, UNCLEAR; if there is no third pass yet, PENDING.
    Returns (label, how) with how in agree / third / split / pending."""
    p = row["passes"]
    a, b = p[0][cutoff]["label"], p[1][cutoff]["label"]
    if a == b:
        return a, "agree"
    if len(p) == 3:
        c = p[2][cutoff]["label"]
        return (c, "third") if c in (a, b) else (UNCLEAR, "split")
    return PENDING, "pending"


def needs_third(row):
    """A third pass is needed when the first two passes differ at either cut-off."""
    p = row["passes"]
    return any(p[0][c]["label"] != p[1][c]["label"] for c in CUTOFFS)


def has_items(row):
    """A reply counts as advice when any pass listed at least one item."""
    return any(p["n_items"] > 0 for p in row["passes"])


def readable(label):
    return label not in (UNCLEAR, PENDING, None)


# --------------------------------------------------------------------------- #
# Labelling-pass agreement
# --------------------------------------------------------------------------- #

def labelling(rows):
    pool = [r for r in rows if r["status"] == "ok"]
    out = {"pool": len(pool), "labellings": sum(len(r["passes"]) for r in pool)}
    for cutoff in CUTOFFS:
        same = [r["passes"][0][cutoff]["label"] == r["passes"][1][cutoff]["label"] for r in pool]
        out[cutoff + "_agree"] = (sum(same), len(pool))
    # An action label (section 8, check 1): at the strict cut-off, either of the
    # first two passes gives a label other than NO CHANGE; UNCLEAR and
    # NO PREFERENCE count as action labels.
    action = [r for r in pool
              if any(r["passes"][i]["strict"]["label"] != NO_CHANGE for i in (0, 1))]
    out["action_agree"] = (
        sum(r["passes"][0]["strict"]["label"] == r["passes"][1]["strict"]["label"] for r in action),
        len(action))
    third = [r for r in pool if needs_third(r)]
    out["third_needed"] = [r["reply_id"] for r in third]
    out["third_missing"] = [r["reply_id"] for r in third if len(r["passes"]) < 3]
    out["three_way_splits"] = [r["reply_id"] for r in third if len(r["passes"]) == 3
                               and any(resolve(r, c)[1] == "split" for c in CUTOFFS)]
    k, n = out["strict_agree"]
    ka, na = out["action_agree"]
    out["pass_all"] = n > 0 and F(k, n) >= AGREE_ALL
    # With fewer than MIN_ACTION_POOL such replies, one or two boundary calls
    # would decide the run, so the minimum is reported but not enforced.
    out["action_tested"] = na >= MIN_ACTION_POOL
    out["pass_action"] = not out["action_tested"] or F(ka, na) >= AGREE_ACTION
    return out


# --------------------------------------------------------------------------- #
# Naive rules
# --------------------------------------------------------------------------- #

def rule_a(week, rows, cutoff):
    """Previous numbered check-in; if its label is unreadable, the nearest
    earlier one with a readable label. Returns (label, source, doubtful): the
    week is doubtful when there was nothing readable to copy, or when at least
    one unreadable label was skipped to reach what was copied."""
    earlier = [r for r in rows if r["kind"] in CHECKIN_KINDS and r["week"] < week]
    skipped = False
    for r in sorted(earlier, key=lambda r: -r["week"]):
        label = resolve(r, cutoff)[0]
        if readable(label):
            return label, r["reply_id"], skipped
        skipped = True
    return None, None, True


def rule_b(original, rows, cutoff):
    """Most recent reply in the replay's own history with at least one item
    and a readable label. If there is none, fall back to rule (a).
    Returns (label, source, fell_back_to_a, doubtful). Replies with no items
    are passed over before readability is tested, so they never make a week
    doubtful; an unreadable reply with items does, and so does falling back
    to (a) when (a) is doubtful."""
    history = [r for r in rows if r["kind"] in HISTORY_KINDS and r["chat"] == original["chat"]
               and r["position"] < original["position"]]
    skipped = False
    for r in sorted(history, key=lambda r: -r["position"]):
        if not has_items(r):
            continue
        label = resolve(r, cutoff)[0]
        if readable(label):
            return label, r["reply_id"], False, skipped
        skipped = True
    label, source, doubtful = rule_a(original["week"], rows, cutoff)
    return label, source, True, skipped or doubtful


# --------------------------------------------------------------------------- #
# Scoring at one cut-off
# --------------------------------------------------------------------------- #

def score_week(week, rows, cutoff, expected):
    original = next(r for r in rows if r["kind"] == "original" and r["week"] == week)
    label, how = resolve(original, cutoff)
    replays = [r for r in rows if r["kind"] == "replay" and r["week"] == week]
    valid = [r for r in replays if r["status"] == "ok"]
    counts = Counter(resolve(r, cutoff)[0] for r in valid)
    clear = {lab: c for lab, c in counts.items() if readable(lab)}
    n, n_clear = len(valid), sum(clear.values())
    rec = {"week": week, "date": original["date"].isoformat(), "original": label,
           "original_how": how, "n_valid": n, "n_readable": n_clear,
           "n_failed": len(replays) - n, "resends": sum(r["attempts"] - 1 for r in replays),
           "replays": dict(counts), "excluded": None, "flags": [],
           "score": None, "share": None, "pairwise": None, "rules": {}}
    if label == PENDING:
        rec["excluded"] = "original awaits a third pass"
    elif label == UNCLEAR:
        rec["excluded"] = "original is UNCLEAR"
    elif n < MIN_SAMPLES:
        rec["excluded"] = f"only {n} valid replays (minimum {MIN_SAMPLES})"
    elif n_clear < MIN_SAMPLES:
        rec["excluded"] = f"only {n_clear} readable replays (minimum {MIN_SAMPLES})"
    if rec["excluded"]:
        return rec

    # The most common label is taken among readable replays only. Unreadable
    # replays stay in the denominators of the share and of the pairs.
    top = max(clear.values())
    tied = sorted(lab for lab, c in clear.items() if c == top)
    rec["top"], rec["top_count"] = tied, top
    rec["score"] = F(1, len(tied)) if label in tied else F(0)
    rec["share"] = F(clear.get(label, 0), n)
    rec["pairwise"] = F(sum(c * (c - 1) for c in clear.values()), n * (n - 1))

    pa, sa, da = rule_a(week, rows, cutoff)
    pb, sb, fell_back, db = rule_b(original, rows, cutoff)
    rec["rules"] = {
        "a": {"pred": pa, "source": sa, "hit": int(pa == label), "doubtful": da},
        "b": {"pred": pb, "source": sb, "hit": int(pb == label), "fell_back_to_a": fell_back,
              "doubtful": db},
        "c": {"pred": NO_CHANGE, "source": None, "hit": int(label == NO_CHANGE), "doubtful": False},
    }
    if n < expected:
        rec["flags"].append(f"reduced to {n} samples")
    if F(top, n) <= UNSTABLE:
        rec["flags"].append("split")
    if F(top, n) >= FIRM and len(tied) == 1 and tied[0] != label:
        rec["flags"].append("firm miss")
    if n_clear < n:
        rec["flags"].append("unreadable replay")
    return rec


def wilson(successes, n, z=1.96):
    if n == 0:
        return None
    p = float(successes) / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap(weeks):
    """Moving-block bootstrap over scoreable weeks in week order.

    Blocks are BLOCK consecutive scoreable weeks. Each resample redraws blocks
    with replacement up to the original number of weeks and recomputes score,
    bar (best of the three rules on the resampled weeks) and margin."""
    n = len(weeks)
    if n < BLOCK:
        return None
    # Week scores are 1/k with k at most 7 labels, so 420ths are exact integers.
    unit = 420
    series = {"score": [int(w["score"] * unit) for w in weeks]}
    assert all(F(v, unit) == w["score"] for v, w in zip(series["score"], weeks))
    for rule in RULES:
        series[rule] = [w["rules"][rule]["hit"] * unit for w in weeks]
    rng = random.Random(SEED)
    starts = n - BLOCK + 1
    draws = {"score": [], "bar": [], "margin": []}
    for _ in range(RESAMPLES):
        index = []
        while len(index) < n:
            start = int(rng.random() * starts)
            index.extend(range(start, start + BLOCK))
        index = index[:n]
        s = sum(series["score"][i] for i in index)
        bar = max(sum(series[rule][i] for i in index) for rule in RULES)
        draws["score"].append(s)
        draws["bar"].append(bar)
        draws["margin"].append(s - bar)
    out = {}
    for key, values in draws.items():
        values.sort()
        lo = values[max(0, math.ceil(PCT_LO * RESAMPLES) - 1)]
        hi = values[max(0, math.ceil(PCT_HI * RESAMPLES) - 1)]
        out[key] = (F(lo, unit), F(hi, unit))
    return out


def score_cutoff(weeks, rows, cutoff, expected):
    table = [score_week(w, rows, cutoff, expected) for w in weeks]
    ok = [w for w in table if not w["excluded"]]
    n = len(ok)
    res = {"cutoff": cutoff, "weeks": table, "n_scoreable": n,
           "excluded": [(w["week"], w["excluded"]) for w in table if w["excluded"]]}
    res["score"] = sum((w["score"] for w in ok), F(0))
    res["rule_totals"] = {rule: sum(w["rules"][rule]["hit"] for w in ok) for rule in RULES}
    res["bar"] = max(res["rule_totals"].values()) if n else 0
    # Ties between rules for the bar go to a, then b, then c.
    res["bar_rule"] = next((r for r in RULES if res["rule_totals"][r] == res["bar"]), None) if n else None
    res["margin"] = res["score"] - res["bar"]
    # A rule's doubtful weeks (nothing readable to copy, or an unreadable label
    # skipped to reach what it copied) are scored as they fall, which can lower
    # the bar. The Opus branch must also hold when every doubtful week counts
    # as a hit for that rule.
    generous = {rule: sum(1 if w["rules"][rule]["doubtful"] else w["rules"][rule]["hit"]
                          for w in ok) for rule in RULES}
    res["rule_totals_generous"] = generous
    res["bar_generous"] = max(generous.values()) if n else 0
    res["margin_generous"] = res["score"] - res["bar_generous"]
    res["margin_needed"] = max(F(MARGIN), MARGIN_SHARE * n)
    change = [w for w in ok if w["rules"][res["bar_rule"]]["hit"] == 0] if n else []
    other = [w for w in ok if w not in change]
    for w in change:
        w["flags"].insert(0, "change week")
    res["change"] = {"weeks": [w["week"] for w in change],
                     "won": sum((w["score"] for w in change), F(0)),
                     "other_weeks": len(other),
                     "other_won": sum((w["score"] for w in other), F(0))}
    originals = Counter(w["original"] for w in ok)
    if originals:
        lab, cnt = sorted(originals.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        res["dominance"] = {"label": lab, "count": cnt, "triggered": F(cnt, n) >= DOMINANCE}
    else:
        res["dominance"] = {"label": None, "count": 0, "triggered": False}
    res["wilson"] = wilson(res["score"], n)
    res["bootstrap"] = bootstrap(ok)
    if n:
        res["mean_share"] = sum((w["share"] for w in ok), F(0)) / n
        res["mean_pairwise"] = sum((w["pairwise"] for w in ok), F(0)) / n
        res["gap"] = res["mean_pairwise"] - res["mean_share"]
    else:
        res["mean_share"] = res["mean_pairwise"] = res["gap"] = None
    res["unreadable_replays"] = sum(c for w in table for lab, c in w["replays"].items()
                                    if not readable(lab))
    return res


# --------------------------------------------------------------------------- #
# Yardstick: the same numbered check-in in the two chats
# --------------------------------------------------------------------------- #

def yardstick(rows, cutoff):
    pairs = []
    for old in sorted((r for r in rows if r["kind"] == "yardstick_old"), key=lambda r: r["week"]):
        new = next((r for r in rows if r["kind"] == "original" and r["chat"] == "NEW"
                    and r["week"] == old["week"]), None)
        if new is None:
            new = next((r for r in rows if r["kind"] == "yardstick_new"
                        and r["week"] == old["week"]), None)
        if new is None:
            continue
        lo, ln = resolve(old, cutoff)[0], resolve(new, cutoff)[0]
        both = readable(lo) and readable(ln)
        pairs.append({"week": old["week"], "old": lo, "new": ln,
                      "old_date": old["date"].isoformat(), "new_date": new["date"].isoformat(),
                      "days_apart": abs((old["date"] - new["date"]).days),
                      "match": (lo == ln) if both else None})
    scored = [p for p in pairs if p["match"] is not None]
    same_day = [p for p in scored if p["days_apart"] == 0]
    return {"pairs": pairs,
            "matched": sum(p["match"] for p in scored), "scored": len(scored),
            "same_day_matched": sum(p["match"] for p in same_day), "same_day": len(same_day)}


# --------------------------------------------------------------------------- #
# The branch: the only decision this script makes
# --------------------------------------------------------------------------- #

def branch(strict, lab, stage="A"):
    """Return (branch, reason). Checked in this order, on strict figures:
    labelling minimums; missing third passes; too few scoreable weeks; low
    score (stop, whether or not one label dominates); one label dominating;
    high with the margin (Opus 4.6); everything else, more weeks.
    At the extension stage "more weeks" is final and reads INCONCLUSIVE."""
    k, n = lab["strict_agree"]
    ka, na = lab["action_agree"]
    if not lab["pass_all"]:
        return "NO DECISION", (f"labelling passes agree on {k} of {n} replies, "
                               f"below the {pct(AGREE_ALL)} minimum")
    if not lab["pass_action"]:
        return "NO DECISION", (f"labelling passes agree on {ka} of {na} replies with an action "
                               f"label, below the {pct(AGREE_ACTION)} minimum")
    if lab["third_missing"]:
        return "NO DECISION", f"{len(lab['third_missing'])} replies still need a third labelling pass"
    more = "EXTENSION" if stage == "A" else "INCONCLUSIVE"
    final = "" if stage == "A" else "; a second extension is not run"
    weeks, s, bar = strict["n_scoreable"], strict["score"], strict["bar"]
    if weeks < MIN_WEEKS:
        return more, f"only {weeks} scoreable weeks (minimum {MIN_WEEKS}); result not read" + final
    dom, needed = strict["dominance"], strict["margin_needed"]
    summary = (f"score {num(s)} of {weeks}, bar {bar} (rule {strict['bar_rule']}), "
               f"margin {num(strict['margin'])}")
    dominated = f"{dom['label']} covers {dom['count']} of {weeks} originals"
    if s <= LOW * weeks:
        return "STOP", (summary + f"; score is at or below {pct(LOW)}"
                        + (f"; {dominated}" if dom["triggered"] else ""))
    if dom["triggered"]:
        return more, dominated + "; " + summary + final
    high = s >= HIGH * weeks
    if high and strict["margin"] >= needed and strict["margin_generous"] >= needed:
        return "OPUS 4.6", summary + f"; high and at least {num(needed)} above the bar"
    if high and strict["margin"] >= needed:
        return more, (summary + f"; high, but the margin is {num(strict['margin_generous'])} when a "
                      "naive rule's doubtful weeks are given the benefit of the doubt" + final)
    if high:
        return more, summary + f"; high but less than {num(needed)} above the bar" + final
    return more, summary + f"; between {pct(LOW)} and {pct(HIGH)}" + final


# --------------------------------------------------------------------------- #
# Run and report
# --------------------------------------------------------------------------- #

def run(manifest):
    weeks, rows, expected, stage = load(manifest)
    # Labelling agreement is also computed over the replays alone (the Opus
    # branch reads that line); the branch below keeps using the pool.
    result = {"weeks": weeks, "stage": stage, "labelling": labelling(rows),
              "labelling_replays": labelling([r for r in rows if r["kind"] == "replay"]),
              "strict": score_cutoff(weeks, rows, "strict", expected),
              "loose": score_cutoff(weeks, rows, "loose", expected),
              "yardstick": {c: yardstick(rows, c) for c in CUTOFFS},
              "kinds": dict(Counter(r["kind"] for r in rows)),
              "failed_replays": sum(r["status"] == "failed" for r in rows),
              "resends": sum(r["attempts"] - 1 for r in rows if r["kind"] == "replay")}
    result["branch"], result["reason"] = branch(result["strict"], result["labelling"], stage)
    return result


def num(x):
    if x is None:
        return "-"
    return f"{float(x):.2f}".rstrip("0").rstrip(".")


def pct(x):
    return "-" if x is None else f"{float(x) * 100:.0f}%"


def ratio(k, n):
    return f"{k} of {n}" + (f" ({pct(F(k, n))})" if n else "")


def _counts(counter):
    order = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return " ".join(f"{SHORT[lab]}{c}" for lab, c in order) or "-"


def _week_lines(res):
    lines = ["  week  date        original       replays          n  score  share  pair   a    b    c    notes",
             "  ----  ----------  -------------  ---------------  -  -----  -----  -----  ---  ---  ---  -----"]
    for w in res["weeks"]:
        head = f"  {w['week']:<4}  {w['date']}  {w['original']:<13}  {_counts(w['replays']):<15}  {w['n_valid']}"
        if w["excluded"]:
            lines.append(head + f"  excluded: {w['excluded']}")
            continue
        cells = []
        for rule in RULES:
            r = w["rules"][rule]
            cells.append((SHORT[r["pred"]] if r["pred"] else "--") + ("+" if r["hit"] else "-"))
        notes = list(w["flags"])
        if w["rules"]["b"]["fell_back_to_a"]:
            notes.append("b fell back to a")
        doubtful = [rule for rule in RULES if w["rules"][rule]["doubtful"]]
        if doubtful:
            notes.append("doubtful: " + ", ".join(doubtful))
        if w["original_how"] != "agree":
            notes.append("original by third pass")
        lines.append(head + f"  {num(w['score']):<5}  {num(w['share']):<5}  {num(w['pairwise']):<5}  "
                     + "  ".join(f"{c:<3}" for c in cells) + "  " + ", ".join(notes))
    return lines


def _interval(pair):
    return "-" if pair is None else f"{num(pair[0])} to {num(pair[1])}"


def report(result, header=()):
    s, l, lab = result["strict"], result["loose"], result["labelling"]
    out = ["REPLAY FIDELITY SCORE"]
    out += list(header)
    out += ["Abbreviations: BN buy now, SN sell now, LI lean in, PB pull back, NC no change,",
            "NP no preference, UN unclear. In rule columns, + is a hit and - a miss.", ""]

    out.append("1. LABELLING PASSES")
    out.append(f"  Stage: {result['stage']}. Pool: {lab['pool']} labelled replies "
               f"({lab['labellings']} labellings); {result['failed_replays']} failed replays "
               f"not labelled; {result['resends']} resends.")
    out.append("  By kind: " + ", ".join(f"{k} {v}" for k, v in sorted(result["kinds"].items())))
    # Two lines with the same definitions and minimums: the whole pool, which
    # decides the branch, and the replays alone, which the Opus branch reads.
    for name, part in (("pool", lab), ("replays only", result["labelling_replays"])):
        verdict = ("pass" if part["pass_action"] else "FAIL") if part["action_tested"] else (
            f"not enforced, fewer than {MIN_ACTION_POOL} such replies")
        out.append(f"  labelling agreement: {name}: same strict label in both passes "
                   f"{ratio(*part['strict_agree'])}, minimum {pct(AGREE_ALL)}: "
                   f"{'pass' if part['pass_all'] else 'FAIL'}; replies with an action label "
                   f"{ratio(*part['action_agree'])}, minimum {pct(AGREE_ACTION)}: {verdict}; "
                   f"third pass missing: {len(part['third_missing'])}")
    out.append(f"  Same loose label in both passes: {ratio(*lab['loose_agree'])}")
    out.append(f"  Third pass needed: {len(lab['third_needed'])}"
               + (": " + ", ".join(lab["third_needed"]) if lab["third_needed"] else ""))
    if lab["third_missing"]:
        out.append("  Third pass MISSING: " + ", ".join(lab["third_missing"]))
    if lab["three_way_splits"]:
        out.append("  All three passes differ (UNCLEAR): " + ", ".join(lab["three_way_splits"]))
    out.append("")

    out.append("2. PER-WEEK TABLE, STRICT (headline)")
    out += _week_lines(s)
    out.append("")

    def both(label, f):
        out.append(f"  {label:<46} strict {f(s):<26} loose {f(l)}")

    out.append("3. NAIVE RULES AND THE BAR")
    for rule in RULES:
        both(f"({rule}) {RULE_NAMES[rule]}", lambda r, rule=rule: f"{r['rule_totals'][rule]} of {r['n_scoreable']}")
    both("Bar (best naive rule; ties go to a, b, c)", lambda r: f"{r['bar']} (rule {r['bar_rule']})")
    both("Bar if each rule's doubtful weeks are hits", lambda r: str(r["bar_generous"]))
    out.append("")

    out.append("4. SCORE AND MARGIN")
    both("Scoreable weeks", lambda r: str(r["n_scoreable"]))
    both("Score", lambda r: f"{num(r['score'])} of {r['n_scoreable']}"
         + (f" ({pct(r['score'] / r['n_scoreable'])})" if r["n_scoreable"] else ""))
    both("Margin over the bar", lambda r: num(r["margin"]))
    both("Margin with that benefit of the doubt", lambda r: num(r["margin_generous"]))
    both("Margin needed for the Opus branch", lambda r: num(r["margin_needed"]))
    for r in (s, l):
        for week, why in r["excluded"]:
            out.append(f"  Excluded at {r['cutoff']}: week {week}, {why}")
    out.append("")

    out.append("5. CHANGE WEEKS (weeks the bar rule gets wrong)")
    both("Change weeks", lambda r: ", ".join(f"#{w}" for w in r["change"]["weeks"]) or "none")
    both("Matched on change weeks", lambda r: f"{num(r['change']['won'])} of {len(r['change']['weeks'])}")
    both("Matched on the other weeks", lambda r: f"{num(r['change']['other_won'])} of {r['change']['other_weeks']}")
    out.append("")

    out.append("6. UNCERTAINTY")
    both("Wilson 95% (a floor; assumes independence)",
         lambda r: "-" if r["wilson"] is None else f"{r['wilson'][0] * 100:.0f}% to {r['wilson'][1] * 100:.0f}%")
    for key, name in (("score", "score"), ("bar", "bar"), ("margin", "margin")):
        both(f"Block bootstrap, middle 90%, {name}",
             lambda r, key=key: "-" if r["bootstrap"] is None else _interval(r["bootstrap"][key]))
    out.append(f"  Blocks of {BLOCK} consecutive scoreable weeks, {RESAMPLES} resamples, seed {SEED}.")
    out.append("")

    out.append("7. DOMINANCE (one label on most originals)")
    both("Most common original label",
         lambda r: f"{r['dominance']['label']} {r['dominance']['count']} of {r['n_scoreable']}"
         + (" TRIGGERED" if r["dominance"]["triggered"] else ""))
    out.append("")

    out.append("8. REPLAY-TO-ORIGINAL BESIDE REPLAY-TO-REPLAY (mean over scoreable weeks)")
    both("Share of replays matching the original", lambda r: num(r["mean_share"]))
    both("Share of replay pairs matching each other", lambda r: num(r["mean_pairwise"]))
    both("Gap (pairs minus original)", lambda r: num(r["gap"]))
    both("Replays with an unreadable label", lambda r: str(r["unreadable_replays"]))
    out.append("")

    out.append("9. YARDSTICK (same numbered check-in in both chats; description only)")
    ys, yl = result["yardstick"]["strict"], result["yardstick"]["loose"]
    if not ys["pairs"]:
        out.append("  No yardstick rows in the manifest.")
    for ps, pl in zip(ys["pairs"], yl["pairs"]):
        def mark(p):
            return "unreadable" if p["match"] is None else ("match" if p["match"] else "differ")
        out.append(f"  #{ps['week']}: NEW {ps['new_date']} {SHORT[ps['new']]} | OLD {ps['old_date']} "
                   f"{SHORT[ps['old']]} | {ps['days_apart']} days apart | strict {mark(ps)}, loose {mark(pl)}")
    if ys["pairs"]:
        out.append(f"  Strict: {ys['matched']} of {ys['scored']} match; same-day pairs "
                   f"{ys['same_day_matched']} of {ys['same_day']}.")
        out.append(f"  Loose:  {yl['matched']} of {yl['scored']} match; same-day pairs "
                   f"{yl['same_day_matched']} of {yl['same_day']}.")
    out.append("")

    out.append("10. PER-WEEK TABLE, LOOSE (reported beside the headline; does not decide)")
    out += _week_lines(l)
    out.append("")
    out.append(f"BRANCH: {result['branch']} | {result['reason']}")
    return "\n".join(out)


def _plain(x):
    if isinstance(x, F):
        return float(x)
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


# --------------------------------------------------------------------------- #
# Invented manifests for the example and the self-tests
# --------------------------------------------------------------------------- #
LI, NC, BN, SN, PB, NP, UN = "LEAN IN", "NO CHANGE", "BUY NOW", "SELL NOW", "PULL BACK", "NO PREFERENCE", "UNCLEAR"


def _passes(spec, n_items=1):
    """spec: a label (both passes agree), or a tuple of two or three labels,
    one per pass. Strict and loose carry the same label unless spec is a dict
    {'strict': ..., 'loose': ...} of such specs."""
    if isinstance(spec, dict):
        strict, loose = spec["strict"], spec["loose"]
    else:
        strict = loose = spec
    strict = (strict, strict) if isinstance(strict, str) else tuple(strict)
    loose = (loose, loose) if isinstance(loose, str) else tuple(loose)
    width = max(len(strict), len(loose))
    strict += (strict[-1],) * (width - len(strict))
    loose += (loose[-1],) * (width - len(loose))
    return [{"pass": i + 1, "n_items": n_items,
             "strict": {"label": strict[i], "tie_break": None, "unclear_reason": None},
             "loose": {"label": loose[i], "tie_break": None, "unclear_reason": None}}
            for i in range(width)]


def _manifest(originals, replays, old9=NC, framework=(LI, 1), interim=(), yard_old=(),
              failed=None, weeks=None, stage="A"):
    """Build an invented manifest. originals: {week: spec}. replays: {week: [spec, ...]}.
    interim: [(position, spec, n_items)]. yard_old: [(week, spec, iso date)].
    failed: {week: number of failed samples}. Check-in for week w sits at position 10*(w-9)."""
    weeks = sorted(originals) if weeks is None else list(weeks)
    day = lambda w: date.fromordinal(date(2011, 8, 19).toordinal() + 7 * (w - 10)).isoformat()
    rows = [{"reply_id": "old9", "kind": "old9", "week": 9, "chat": "OLD", "date": "2042-09-12",
             "position": 28, "sample": None, "passes": _passes(old9)},
            {"reply_id": "framework", "kind": "framework", "week": None, "chat": "NEW",
             "date": "2016-06-17", "position": 2, "sample": None,
             "passes": _passes(framework[0], framework[1])}]
    for w, spec in sorted(originals.items()):
        rows.append({"reply_id": f"orig{w}", "kind": "original", "week": w, "chat": "NEW",
                     "date": day(w), "position": 10 * (w - 9), "sample": None, "passes": _passes(spec)})
    for w, specs in sorted(replays.items()):
        for i, spec in enumerate(specs, 1):
            rows.append({"reply_id": f"rep{w}_{i}", "kind": "replay", "week": w, "chat": "NEW",
                         "date": day(w), "position": None, "sample": i, "attempts": 1,
                         "passes": _passes(spec)})
        for j in range((failed or {}).get(w, 0)):
            rows.append({"reply_id": f"rep{w}_f{j + 1}", "kind": "replay", "week": w, "chat": "NEW",
                         "date": day(w), "position": None, "sample": len(specs) + j + 1,
                         "attempts": MAX_ATTEMPTS, "status": "failed", "passes": []})
    for pos, spec, n_items in interim:
        rows.append({"reply_id": f"interim{pos}", "kind": "interim", "week": None, "chat": "NEW",
                     "date": "2041-02-01", "position": pos, "sample": None,
                     "passes": _passes(spec, n_items)})
    for w, spec, iso in yard_old:
        rows.append({"reply_id": f"yard{w}", "kind": "yardstick_old", "week": w, "chat": "OLD",
                     "date": iso, "position": None, "sample": None, "passes": _passes(spec)})
    return {"run": {"name": "invented", "weeks": weeks, "samples_per_week": 5, "stage": stage},
            "replies": rows}


WEEKS = range(10, 20)
VARIED = dict(zip(WEEKS, [LI, NC, BN, NC, LI, NC, PB, NC, LI, NC]))   # rule c gets 5
MOSTLY_NC = dict(zip(WEEKS, [NC, NC, LI, NC, NC, NC, LI, NC, NC, LI]))  # rule c gets 7


def _replays(originals, misses=(), with_label=LI, overrides=None):
    """Five replays per week that all match the original, except in `misses`,
    where all five carry `with_label` (or NO CHANGE if that is the original)."""
    out = {}
    for w, lab in originals.items():
        lab = lab if isinstance(lab, str) else NC
        wrong = with_label if lab != with_label else NC
        out[w] = [wrong if w in misses else lab] * 5
    out.update(overrides or {})
    return out


def example_manifest():
    return _manifest(VARIED, _replays(VARIED, misses=(19,)),
                     interim=[(55, NC, 0), (57, LI, 2)],
                     yard_old=[(10, LI, "2011-08-15"), (11, LI, "2011-08-22"),
                               (12, BN, "2011-08-27"), (13, NC, "2011-09-09")])


def selftest():
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    # 1. Clean pass to each branch.
    r = run(example_manifest())
    check("opus: score 9, bar 5 by rule c, margin 4",
          (r["strict"]["score"], r["strict"]["bar"], r["strict"]["bar_rule"], r["strict"]["margin"]) == (9, 5, "c", 4))
    check("opus: branch", r["branch"] == "OPUS 4.6")
    check("opus: change weeks are the five non-NO-CHANGE weeks, all matched",
          r["strict"]["change"]["weeks"] == [10, 12, 14, 16, 18] and r["strict"]["change"]["won"] == 5
          and r["strict"]["change"]["other_won"] == 4)
    check("margin equals change weeks won minus other weeks lost",
          r["strict"]["margin"] == r["strict"]["change"]["won"]
          - (r["strict"]["change"]["other_weeks"] - r["strict"]["change"]["other_won"]))

    r = run(_manifest(MOSTLY_NC, _replays(MOSTLY_NC, misses=(19,))))
    check("extension (high, close to bar): score 9, bar 7, margin 2",
          (r["strict"]["score"], r["strict"]["bar"], r["branch"]) == (9, 7, "EXTENSION"))
    r = run(_manifest(VARIED, _replays(VARIED, misses=(17, 18, 19))))
    check("extension (in between): score 7", (r["strict"]["score"], r["branch"]) == (7, "EXTENSION"))
    r = run(_manifest(VARIED, _replays(VARIED, misses=(15, 16, 17, 18, 19))))
    check("stop: score 5 of 10", (r["strict"]["score"], r["branch"]) == (5, "STOP"))

    # 2. Ties among the five, and unreadable replays.
    ties = _replays(VARIED, overrides={10: [LI, LI, NC, NC, BN],      # original LI: two-way tie
                                       11: [LI, BN, NC, PB, SN],      # original NC: five-way tie
                                       12: [BN, BN, UN, UN, NC],      # original BN: top among readable
                                       13: [NC, NC, UN, UN, UN]})     # only two readable replays
    r = run(_manifest(VARIED, ties))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("two-way tie scores 1/2", wk[10]["score"] == F(1, 2) and wk[10]["share"] == F(2, 5))
    check("five-way tie scores 1/5", wk[11]["score"] == F(1, 5))
    check("unreadable replays cannot be the top label but stay in the denominators",
          wk[12]["score"] == 1 and wk[12]["share"] == F(2, 5) and wk[12]["pairwise"] == F(2, 20)
          and "unreadable replay" in wk[12]["flags"])
    check("fewer than three readable replays: week excluded",
          wk[13]["excluded"] == "only 2 readable replays (minimum 3)")
    check("tie week total", r["strict"]["score"] == 6 + F(1, 2) + F(1, 5) + 1
          and r["strict"]["n_scoreable"] == 9)
    check("split flag on a 2-2-1 week", "split" in wk[10]["flags"])

    # 3. UNCLEAR original: week excluded, thresholds as shares of what remains.
    originals = dict(VARIED)
    originals[19] = UN
    r = run(_manifest(originals, _replays(originals, overrides={18: [LI, LI, NC, NC, BN], 19: [NC] * 5})))
    check("unclear original excluded: 9 weeks", r["strict"]["n_scoreable"] == 9
          and r["strict"]["excluded"] == [(19, "original is UNCLEAR")])
    check("8.5 of 9 with bar 4 goes to opus", (r["strict"]["score"], r["strict"]["bar"], r["branch"])
          == (F(17, 2), 4, "OPUS 4.6"))

    # 4. Sample minimum: 3 valid replays are scored, 2 are not.
    r = run(_manifest(VARIED, _replays(VARIED, overrides={18: [LI, LI, NC], 19: [NC, NC]}),
                      failed={18: 2, 19: 3}))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("three valid replays: scored and flagged", wk[18]["score"] == 1 and wk[18]["share"] == F(2, 3)
          and "reduced to 3 samples" in wk[18]["flags"] and wk[18]["n_failed"] == 2)
    check("two valid replays: week excluded", wk[19]["excluded"] == "only 2 valid replays (minimum 3)")
    check("failed replays counted", r["failed_replays"] == 5)

    # 5. Fewer than 8 scoreable weeks: extension without reading the result.
    r = run(_manifest(VARIED, _replays(VARIED, overrides={17: [NC], 18: [LI], 19: []}),
                      failed={17: 4, 18: 4, 19: 5}))
    check("seven scoreable weeks: extension", r["strict"]["n_scoreable"] == 7 and r["branch"] == "EXTENSION"
          and "result not read" in r["reason"])

    # 6. Labelling passes.
    noisy = {w: [(lab, NC if lab != NC else LI)] * 2 + [lab] * 3 for w, lab in VARIED.items()}
    r = run(_manifest(VARIED, noisy))
    check("overall agreement below 85%: no decision",
          r["labelling"]["strict_agree"] == (42, 62) and r["branch"] == "NO DECISION")
    # 62 replies with 6 disagreements, all on replies where one pass gives an
    # action label: overall 56 of 62 passes, the action-label subset 13 of 19 fails.
    few = _replays(MOSTLY_NC, overrides={w: [(LI, NC), (LI, NC), LI, LI, LI] for w in (12, 16, 19)})
    r = run(_manifest(MOSTLY_NC, few))
    check("action-label agreement below 70%: no decision",
          r["labelling"]["strict_agree"] == (56, 62) and r["labelling"]["action_agree"] == (13, 19)
          and r["labelling"]["pass_all"] and not r["labelling"]["pass_action"]
          and r["branch"] == "NO DECISION" and "action label" in r["reason"])
    one = _replays(VARIED, misses=(19,), overrides={10: [(LI, NC), LI, LI, LI, LI]})
    r = run(_manifest(VARIED, one))
    check("disagreement without a third pass: no decision, reply listed",
          r["branch"] == "NO DECISION" and r["labelling"]["third_missing"] == ["rep10_1"])
    one[10] = [(LI, NC, LI), (LI, NC, BN), LI, LI, LI]
    r = run(_manifest(VARIED, one))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("third pass: two of three wins, three-way split is UNCLEAR",
          wk[10]["replays"] == {LI: 4, UN: 1} and r["branch"] == "OPUS 4.6"
          and r["labelling"]["three_way_splits"] == ["rep10_2"])
    loose_only = _replays(VARIED, misses=(19,), overrides={
        10: [{"strict": LI, "loose": (LI, BN)}, LI, LI, LI, LI]})
    r = run(_manifest(VARIED, loose_only))
    check("passes differing only at the loose cut-off still need a third pass",
          r["labelling"]["third_missing"] == ["rep10_1"] and r["labelling"]["strict_agree"][0] == 62)

    # 7. Dominance.
    dom = dict(zip(WEEKS, [LI, LI, BN, LI, LI, LI, NC, LI, LI, LI]))
    r = run(_manifest(dom, _replays(dom), framework=(NC, 0)))
    check("dominance: 10 of 10 and margin 5 would be opus, but one label covers 8",
          (r["strict"]["score"], r["strict"]["bar"], r["strict"]["dominance"]["count"]) == (10, 5, 8)
          and r["strict"]["dominance"]["triggered"] and r["branch"] == "EXTENSION")
    r = run(_manifest(dom, _replays(dom, misses=WEEKS), framework=(NC, 0)))
    check("a low score stops even when one label dominates, and the reason says so",
          r["strict"]["score"] == 0 and r["branch"] == "STOP" and "covers 8 of 10" in r["reason"])
    mostly_wait = dict(zip(WEEKS, [NC, NC, NC, BN, NC, NC, NC, NC, NC, NC]))
    r = run(_manifest(mostly_wait, _replays(mostly_wait, misses=(11, 12, 13, 15, 16, 18), with_label=BN),
                      framework=(NC, 0)))
    check("the open case: 4 of 10 against a bar of 9 is STOP",
          (r["strict"]["score"], r["strict"]["bar"], r["branch"]) == (4, 9, "STOP"))
    seven = dict(zip(WEEKS, [LI, LI, BN, LI, LI, LI, NC, LI, PB, LI]))
    r = run(_manifest(seven, _replays(seven), framework=(NC, 0)))
    check("7 of 10 does not trigger dominance", not r["strict"]["dominance"]["triggered"]
          and r["branch"] == "OPUS 4.6")

    # 8. Rule (b) walks past replies with no items and past unreadable ones.
    interim = [(61, LI, 2),        # advice: lean in
               (63, UN, 1),        # has an item but the label is unreadable
               (65, NC, 0)]        # reassurance, no items
    r = run(_manifest(VARIED, _replays(VARIED), interim=interim))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("rule b for #16 skips the empty and the unreadable reply",
          wk[16]["rules"]["b"]["pred"] == LI and wk[16]["rules"]["b"]["source"] == "interim61")
    check("rule a for #16 is the previous check-in", wk[16]["rules"]["a"]["source"] == "orig15")
    check("rule b for #10 is the framework reply", wk[10]["rules"]["b"]["source"] == "framework"
          and not wk[10]["rules"]["b"]["fell_back_to_a"])
    r = run(_manifest(VARIED, _replays(VARIED), framework=(NC, 0), old9=PB))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("rule b for #10 falls back to rule a when the framework reply has no item",
          wk[10]["rules"]["b"]["fell_back_to_a"] and wk[10]["rules"]["b"]["pred"] == PB
          and wk[10]["rules"]["b"]["source"] == "old9")
    mixed = _manifest(VARIED, _replays(VARIED), interim=[(65, NC, 0)])
    next(x for x in mixed["replies"] if x["reply_id"] == "interim65")["passes"][1]["n_items"] = 1
    wk = {w["week"]: w for w in run(mixed)["strict"]["weeks"]}
    check("a reply counts as advice when either pass lists an item",
          wk[16]["rules"]["b"]["source"] == "interim65")
    r = run(_manifest(VARIED, _replays(VARIED), old9=UN, framework=(NC, 0)))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("no readable source: the rule has no prediction and misses",
          wk[10]["rules"]["a"]["pred"] is None and wk[10]["rules"]["a"]["hit"] == 0)

    # 9. Other rules of decision 3.
    np_week = dict(VARIED)
    np_week[11] = NP
    r = run(_manifest(np_week, _replays(np_week)))
    check("NO PREFERENCE matches only itself", r["strict"]["score"] == 10)
    split_cutoffs = _replays(VARIED, overrides={19: [{"strict": NC, "loose": BN}] * 5})
    r = run(_manifest(VARIED, split_cutoffs))
    check("loose figures are computed beside strict and do not decide",
          (r["strict"]["score"], r["loose"]["score"], r["branch"]) == (10, 9, "OPUS 4.6"))
    r = run(example_manifest())
    y = r["yardstick"]["strict"]
    check("yardstick: 3 of 4 match, one same-day pair, gaps of 4, 4, 6 and 0 days",
          (y["matched"], y["scored"], y["same_day_matched"], y["same_day"]) == (3, 4, 1, 1)
          and [p["days_apart"] for p in y["pairs"]] == [4, 4, 6, 0])
    w = wilson(8, 10)
    check("Wilson for 8 of 10 is 49% to 94%", (round(w[0] * 100), round(w[1] * 100)) == (49, 94))
    check("pairwise and share coincide when all five agree with the original",
          r["strict"]["weeks"][0]["share"] == 1 and r["strict"]["weeks"][0]["pairwise"] == 1)
    check("mean share 0.9 and mean pairwise 1 in the example",
          r["strict"]["mean_share"] == F(9, 10) and r["strict"]["mean_pairwise"] == 1)

    # 10. Benefit of the doubt for a naive rule's doubtful weeks (ruling of 14 Oct).
    doubt = dict(zip(WEEKS, [LI, LI, LI, BN, BN, NC, NC, PB, PB, LI]))
    reps = _replays(doubt, misses=(18, 19), with_label=NC)
    r = run(_manifest(doubt, reps, old9=LI, framework=(NC, 0)))
    check("readable old9: bar 6, margin 2, extension",
          (r["strict"]["score"], r["strict"]["bar"], r["branch"]) == (8, 6, "EXTENSION"))
    r = run(_manifest(doubt, reps, old9=UN, framework=(NC, 0)))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("unreadable old9 lowers the printed bar to 5 but cannot buy the Opus branch: "
          "week 10 is doubtful for a and b (nothing to copy), and counts as their hit",
          (r["strict"]["bar"], r["strict"]["margin"], r["strict"]["bar_generous"],
           r["strict"]["margin_generous"], r["branch"]) == (5, 3, 6, 2, "EXTENSION")
          and wk[10]["rules"]["a"]["doubtful"] and wk[10]["rules"]["b"]["doubtful"]
          and [w for w in wk if wk[w]["rules"]["a"]["doubtful"] or wk[w]["rules"]["b"]["doubtful"]] == [10]
          and "doubtful weeks are given the benefit of the doubt" in r["reason"])

    # 11. The action-label minimum needs at least ten such replies.
    quiet = dict(zip(WEEKS, [NC] * 9 + [LI]))
    reps = _replays(quiet, overrides={19: [(LI, NC), (LI, NC), LI, LI, LI]})
    r = run(_manifest(quiet, reps, framework=(NC, 0)))
    check("4 of 6 action replies agree: reported, not enforced",
          r["labelling"]["action_agree"] == (4, 6) and not r["labelling"]["action_tested"]
          and r["labelling"]["pass_action"] and r["labelling"]["third_missing"] == ["rep19_1", "rep19_2"])

    # 12. Extension stage: all weeks pooled, margin of 30% of the weeks, and
    #     a second "more weeks" verdict is final.
    W17 = range(10, 27)
    pooled = dict(zip(W17, [LI, NC, BN, NC, LI, NC, PB, NC, LI, NC, BN, NC, LI, NC, PB, NC, LI]))  # rule c: 8
    r = run(_manifest(pooled, _replays(pooled, misses=(26,)), stage="extension"))
    check("pooled 16 of 17 against a bar of 8: Opus", (r["strict"]["score"], r["strict"]["bar"],
          r["strict"]["margin_needed"], r["branch"]) == (16, 8, F(51, 10), "OPUS 4.6"))
    r = run(_manifest(pooled, _replays(pooled, misses=(22, 24, 26)), stage="extension"))
    check("pooled 14 of 17 with a margin of 6 clears the 5.1 needed: Opus",
          (r["strict"]["score"], r["strict"]["margin"], r["branch"]) == (14, 6, "OPUS 4.6"))
    close = dict(zip(W17, [LI, NC, NC, NC, LI, NC, NC, NC, LI, NC, NC, NC, LI, NC, NC, NC, LI]))  # rule c: 12
    r = run(_manifest(close, _replays(close, misses=(26,)), stage="extension"))
    check("pooled 16 of 17 against a bar of 12: margin 4 is short of 5.1, final",
          (r["strict"]["margin"], r["branch"]) == (4, "INCONCLUSIVE") and "second extension" in r["reason"])
    r = run(_manifest(pooled, _replays(pooled, misses=(18, 20, 22, 24, 26)), stage="extension"))
    check("pooled 12 of 17 is in between: final", (r["strict"]["score"], r["branch"]) == (12, "INCONCLUSIVE"))
    r = run(_manifest(pooled, _replays(pooled, misses=range(10, 19)), stage="extension"))
    check("pooled 8 of 17 is low: stop", (r["strict"]["score"], r["branch"]) == (8, "STOP"))
    r = run(_manifest(VARIED, _replays(VARIED, misses=(19,))))
    check("stage A still needs a margin of exactly 3 on ten weeks", r["strict"]["margin_needed"] == 3)

    # 13. Ties between naive rules for the bar go to a, then b, then c.
    tie = dict(zip(WEEKS, [NC, NC, LI, LI, NC, NC, LI, LI, NC, NC]))   # a: 6, c: 6
    r = run(_manifest(tie, _replays(tie), old9=NC, framework=(NC, 0)))
    check("bar tie goes to rule a", r["strict"]["rule_totals"]["a"] == r["strict"]["rule_totals"]["c"] == 6
          and r["strict"]["bar_rule"] == "a")

    # 14. Sample bookkeeping and loader checks.
    def rejected(change):
        bad = example_manifest()
        change(bad)
        try:
            run(bad)
            return False
        except ManifestError:
            return True

    rep10 = lambda m: next(x for x in m["replies"] if x["reply_id"] == "rep10_1")
    check("a sample number above samples_per_week is rejected",
          rejected(lambda m: rep10(m).__setitem__("sample", 6)))
    check("a missing sample row is rejected",
          rejected(lambda m: m["replies"].remove(rep10(m))))
    check("a replay without attempts is rejected", rejected(lambda m: rep10(m).pop("attempts")))
    check("more than three attempts is rejected", rejected(lambda m: rep10(m).__setitem__("attempts", 4)))
    check("a missing previous check-in is rejected",
          rejected(lambda m: m["replies"].remove(next(x for x in m["replies"] if x["kind"] == "old9"))))
    check("a null pass number is a manifest error, not a crash",
          rejected(lambda m: rep10(m)["passes"][0].__setitem__("pass", None)))
    check("samples_per_week as text is a manifest error, not a crash",
          rejected(lambda m: m["run"].__setitem__("samples_per_week", "5")))
    check("a reply that is not an object is a manifest error, not a crash",
          rejected(lambda m: m["replies"].append("oops")))
    check("an unknown stage is rejected", rejected(lambda m: m["run"].__setitem__("stage", "B")))
    m = _manifest(VARIED, _replays(VARIED, overrides={18: [LI, LI, NC]}), failed={18: 2})
    next(x for x in m["replies"] if x["reply_id"] == "rep18_2")["attempts"] = 3
    r = run(m)
    check("resends are counted: two on a kept sample plus two each on two failed ones",
          r["resends"] == 6 and r["failed_replays"] == 2)

    # 15. Determinism and input checks.
    a, b = run(example_manifest()), run(example_manifest())
    check("bootstrap is deterministic", a["strict"]["bootstrap"] == b["strict"]["bootstrap"]
          and report(a) == report(b))
    lo, hi = a["strict"]["bootstrap"]["score"]
    check("bootstrap interval brackets a plausible range", 7 <= lo <= 9 <= hi <= 10)
    perfect = run(_manifest(VARIED, _replays(VARIED)))
    check("bootstrap of a perfect score is 10 to 10", perfect["strict"]["bootstrap"]["score"] == (10, 10))
    bad = example_manifest()
    bad["replies"].append(dict(bad["replies"][0]))
    try:
        run(bad)
        check("duplicate reply_id is rejected", False)
    except ManifestError:
        check("duplicate reply_id is rejected", True)
    bad = example_manifest()
    bad["replies"] = [x for x in bad["replies"] if x["reply_id"] != "orig12"]
    try:
        run(bad)
        check("a scored week without an original is rejected", False)
    except ManifestError:
        check("a scored week without an original is rejected", True)
    bad = example_manifest()
    bad["replies"][5]["passes"][0]["strict"]["label"] = "HOLD"
    try:
        run(bad)
        check("an unknown label is rejected", False)
    except ManifestError:
        check("an unknown label is rejected", True)

    # 16. Doubtful weeks and replays-only agreement (ruling of 14 Oct).
    #     Week 12's original is UNCLEAR, so week 13's rules a and b walk past it.
    walk = dict(zip(WEEKS, [LI, LI, UN, BN, BN, NC, NC, PB, PB, LI]))
    walked = _manifest(walk, _replays(walk, misses=(19,), with_label=NC), old9=LI, framework=(NC, 0))
    r = run(walked)
    s = r["strict"]
    wk = {w["week"]: w for w in s["weeks"]}
    check("rule a walks past an UNCLEAR check-in: copies #11, misses as scored, doubtful",
          (wk[13]["rules"]["a"]["pred"], wk[13]["rules"]["a"]["source"], wk[13]["rules"]["a"]["hit"],
           wk[13]["rules"]["a"]["doubtful"]) == (LI, "orig11", 0, True))
    check("the walked-past week counts as a hit only in the bar with the benefit of the doubt",
          (s["rule_totals"]["a"], s["rule_totals_generous"]["a"], s["bar"], s["bar_generous"]) == (5, 6, 5, 6)
          and [w for w in wk if not wk[w]["excluded"] and wk[w]["rules"]["a"]["doubtful"]] == [13])
    check("the per-week table marks the doubtful rules",
          any(line.startswith("  13 ") and "doubtful: a, b" in line for line in report(r).splitlines()))
    check("a manifest at OPUS 4.6 under the 10 Oct file (score 8 of 9, bar 5, margin 3) "
          "is EXTENSION once the doubtful week counts",
          (s["score"], s["n_scoreable"], s["bar"], s["margin"], s["margin_generous"], r["branch"])
          == (8, 9, 5, 3, 2, "EXTENSION") and "benefit of the doubt" in r["reason"])
    no_walk = dict(walk)
    no_walk[12] = LI
    r = run(_manifest(no_walk, _replays(no_walk, misses=(19,), with_label=NC), old9=LI, framework=(NC, 0)))
    check("the same manifest with a readable #12 has no doubtful week and stays at OPUS 4.6",
          r["branch"] == "OPUS 4.6" and r["strict"]["bar"] == r["strict"]["bar_generous"]
          and not any(w["rules"][x]["doubtful"] for w in r["strict"]["weeks"] for x in RULES))

    r = run(_manifest(VARIED, _replays(VARIED), interim=interim))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("rule b skips an unreadable reply that has items: doubtful",
          wk[16]["rules"]["b"]["source"] == "interim61" and wk[16]["rules"]["b"]["doubtful"]
          and not wk[16]["rules"]["a"]["doubtful"])
    r = run(_manifest(VARIED, _replays(VARIED), interim=[(65, NC, 0)]))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("rule b skipping only replies with no items is not doubtful",
          wk[16]["rules"]["b"]["source"] == "orig15" and not wk[16]["rules"]["b"]["doubtful"])

    r = run(_manifest(VARIED, _replays(VARIED), framework=(NC, 0), old9=PB))
    wk = {w["week"]: w for w in r["strict"]["weeks"]}
    check("rule b falls back to a, and a skipped nothing: not doubtful",
          wk[10]["rules"]["b"]["fell_back_to_a"] and not wk[10]["rules"]["b"]["doubtful"]
          and not wk[10]["rules"]["a"]["doubtful"])
    m = _manifest(VARIED, _replays(VARIED), framework=(NC, 0), old9=UN)
    m["replies"].append({"reply_id": "old8", "kind": "original", "week": 8, "chat": "OLD",
                         "date": "2037-05-27", "position": 26, "sample": None, "passes": _passes(PB)})
    wk = {w["week"]: w for w in run(m)["strict"]["weeks"]}
    check("rule b falls back to a, and a skipped an unreadable check-in: both doubtful",
          wk[10]["rules"]["b"]["fell_back_to_a"] and (wk[10]["rules"]["b"]["pred"], wk[10]["rules"]["b"]["source"])
          == (PB, "old8") and wk[10]["rules"]["a"]["doubtful"] and wk[10]["rules"]["b"]["doubtful"])
    check("rule c is never doubtful", not any(w["rules"]["c"]["doubtful"] for w in wk.values()))

    split = _replays(VARIED, misses=(19,), overrides={11: [(NC, LI, NC), NC, NC, NC, NC]})
    m = _manifest(VARIED, split)
    next(x for x in m["replies"] if x["reply_id"] == "orig10")["passes"] = _passes((LI, NC, LI))
    next(x for x in m["replies"] if x["reply_id"] == "old9")["passes"] = _passes((NC, PB, NC))
    r = run(m)
    lines = report(r).splitlines()
    check("replays-only agreement computed beside the pool's",
          (r["labelling"]["pool"], r["labelling"]["strict_agree"]) == (62, (59, 62))
          and (r["labelling_replays"]["pool"], r["labelling_replays"]["strict_agree"]) == (50, (49, 50))
          and r["branch"] == "OPUS 4.6")
    check("both labelling agreement lines are printed",
          sum(line.startswith("  labelling agreement: pool: same strict label in both passes 59 of 62")
              for line in lines) == 1
          and sum(line.startswith("  labelling agreement: replays only: same strict label in both passes 49 of 50")
                  for line in lines) == 1)
    r = run(_manifest(MOSTLY_NC, few))
    rep = r["labelling_replays"]
    check("replays only: same 70% minimum, enforced from ten action-label replies",
          rep["action_agree"] == (9, 15) and rep["action_tested"] and not rep["pass_action"])
    r = run(_manifest(quiet, _replays(quiet, overrides={19: [(LI, NC, LI), (LI, NC, LI), LI, LI, LI]}),
                      framework=(NC, 0)))
    rep = r["labelling_replays"]
    check("replays only: fewer than ten action-label replies is reported, not enforced",
          rep["action_agree"] == (3, 5) and not rep["action_tested"] and rep["pass_action"])
    m = _manifest(VARIED, _replays(VARIED, overrides={10: [(LI, NC), LI, LI, LI, LI]}))
    next(x for x in m["replies"] if x["reply_id"] == "orig11")["passes"] = _passes((NC, LI))
    r = run(m)
    check("the replays-only third-pass check lists only replays; the branch reads the pool",
          r["labelling"]["third_missing"] == ["orig11", "rep10_1"]
          and r["labelling_replays"]["third_missing"] == ["rep10_1"] and r["branch"] == "NO DECISION")

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("ok   " if ok else "FAIL ") + name)
    print(f"{len(checks) - len(failed)}/{len(checks)} self-tests pass")
    return not failed


# --------------------------------------------------------------------------- #

def main(argv):
    if len(argv) >= 2 and argv[1] == "selftest":
        return 0 if selftest() else 1
    if len(argv) >= 2 and argv[1] == "example":
        print(json.dumps(example_manifest(), indent=1))
        return 0
    if len(argv) >= 3 and argv[1] == "score":
        raw = open(argv[2], "rb").read()
        try:
            result = run(json.loads(raw.decode("utf-8")))
        except ManifestError as err:
            print(f"MANIFEST ERROR: {err}")
            print("BRANCH: NO DECISION | the manifest could not be read")
            return 2
        header = [f"Manifest: {argv[2]}  sha256 {hashlib.sha256(raw).hexdigest()}",
                  f"Script:   sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}", ""]
        print(report(result, header))
        if "--json" in argv:
            path = argv[argv.index("--json") + 1]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_plain(result), fh, indent=1, sort_keys=True)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
