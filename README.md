# Replaying an AI advisor

Does the same model, given the same inputs, give the same weekly call twice?

This repository holds the public, aggregate-only results of a pre-registered experiment run in October 2026. Claude Sonnet 4.6 re-ran, through the API, 17 weekly check-ins of the advisor chats (a first chat, then the one that took over from it) that the author had used for a long-term, staged buying plan in a highly volatile crypto asset. Each check-in was replayed 5 times, and every reply, original and replay alike, was labelled blind by a second model under fixed rules.

**Result: INCONCLUSIVE.** The replays' most common call matched the advisor's in 10 of 17 weeks (59%). "Always no change" matched 7. The registered pass mark needed 80% and a lead of 5.1 weeks; the lead was 3. The replays agreed with each other (0.44 of pairs) about as often as with the advisor (0.47): on these numbers, one weekly answer behaves like one draw from a wide spread of possible answers. The full account is in [`WRITEUP.md`](WRITEUP.md).

## What is here

| Path | What it is |
|---|---|
| `WRITEUP.md` | The write-up: question, design, what happened, aggregate results, the registered reading, limits, lessons |
| `RECORD.md` | Every published file's checksum, and what differs from the file that ran |
| `scoring/score.py` | The scorer: per-week hits, the naive-rule bar, the checks in order, the verdict line. Standard library only |
| `scoring/manifest_schema.json` | The format of the manifest the scorer reads |
| `labeller/labeller_system_prompt.txt` | The labeller's instructions: what counts as a recommendation item and how to describe it |
| `labeller/labeller_schema.json`, `labeller/labeller_request.json` | The structured-output schema and the request settings the labeller ran with |
| `labeller/combine.py` | The fixed rules that turn a labeller's item list into one label per cut-off |
| `labeller/calibration_set.json`, `labeller/heldout_set.json` | The invented replies the labeller was checked on before any real reply |

## What is not here, and why

The conversations, the week-by-week calls, the dates of the check-ins, the replays themselves, the run logs, and everything about the author's plan, positions and accounts are private, and stay that way. So do the registration, the harness that built the requests, its tests, and the session reports, which are full of those details. The private record is kept unchanged; the checksums in `WRITEUP.md` section 10 fix it.

Four published files differ from the versions that ran, only where the originals held private details. The differences are listed in `RECORD.md`:
- `scoring/score.py`: the self-test's invented example weeks were dated on the real check-in calendar; their dates are redrawn, with every self-test result unchanged.
- `labeller/labeller_system_prompt.txt`, `labeller/calibration_set.json`, `labeller/heldout_set.json`: the example prices were at the real asset's scale, and a few sizes and one currency could echo the author's own; they are redrawn as fresh made-up values, so every example still reads the same way and gets the same label.

The checksums of those four files as they ran are kept privately, not published: with them, anyone could test guesses of the original values. `labeller/combine.py`, the two schema files and the request settings are published exactly as they ran.

## Running the checks

Python 3, no packages needed.

```
python3 scoring/score.py selftest
python3 labeller/combine.py selftest
```

The scorer can also be run on a manifest of your own (`python3 scoring/score.py score MANIFEST.json`), or on an invented one (`python3 scoring/score.py example`).

## How it was run

The experiment was planned, built and checked with Claude: a design chat that never saw a reply or a call wrote the rules; a builder agent built and ran the harness; a separate read-only validator agent rebuilt every deciding number from the raw logs with its own code; and every paid step ran only after the author typed a go-ahead. The rules were frozen, with checksums, before the first scored call. `WRITEUP.md` sections 2 and 3 tell the story, including the one bug found after the runs and how it was handled.
