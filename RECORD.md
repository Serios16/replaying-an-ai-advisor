# Record of the published files

Each published file and its SHA-256. For a file published unchanged, the frozen file's SHA-256 (as pinned in the private repository's `SHA256SUMS.txt`) is given, and it is equal to the published one. For a file whose public copy was changed, only literals of the kinds named differ; old and new values are not given, and the checksum of the file as it ran is kept privately.

| Published file | SHA-256 | Status |
|---|---|---|
| `README.md` | `2b6cc1c40c6735ac268400ce50b1a7946a2989ec5f7f231365f8342016a1db1a` | written for the public copy, derived from the private write-up (SHA-256 `11d9e357c3bd46a01a300efd6ac46ab5f3cc7075e11f1139f5b56bfe6199e792`) |
| `WRITEUP.md` | `281eb1ad0f19b8ad17bfdc37d4382722439e50d84ea1a973a84633280f07d981` | written for the public copy, derived from the private write-up (SHA-256 `11d9e357c3bd46a01a300efd6ac46ab5f3cc7075e11f1139f5b56bfe6199e792`) |
| `labeller/combine.py` | `aa84c643ed0f3251bbbad498cc631b1557ea0b113dd91554e1d47f9aee46f901` | unchanged; frozen SHA-256 `aa84c643ed0f3251bbbad498cc631b1557ea0b113dd91554e1d47f9aee46f901` |
| `labeller/labeller_schema.json` | `f0e76852eae47e503b600a2cf1d2d2987ec4db521bc0d7b76dcfa27634caa52f` | unchanged; frozen SHA-256 `f0e76852eae47e503b600a2cf1d2d2987ec4db521bc0d7b76dcfa27634caa52f` |
| `labeller/labeller_request.json` | `8637fc7d5214c55917d0889c912983509665adb0df100da7f1ebad758134e0fb` | unchanged; frozen SHA-256 `8637fc7d5214c55917d0889c912983509665adb0df100da7f1ebad758134e0fb` (see note 1) |
| `scoring/manifest_schema.json` | `55f34fcd6582b5e55ea3afd43672856d4de9069e4a98094b9a31596b40920848` | unchanged; frozen SHA-256 `55f34fcd6582b5e55ea3afd43672856d4de9069e4a98094b9a31596b40920848` |
| `scoring/score.py` | `25c77e5b273f82673a8242a0437935b419cb5cba40cee66c98b239804607b065` | changed: self-test and example dates, 9 literals (8 date strings and the one date the invented weeks are counted from), freshly drawn, not computed from the old values; the checksum of the file as it ran is kept privately |
| `labeller/labeller_system_prompt.txt` | `26a3401f74710731472f4f006afb485d384eac465b1191d3f8839300377c0b84` | changed: example prices, 22 literals (20 with a k suffix, 2 written in full), and 1 currency amount in a size example, freshly drawn, not computed from the old values; the checksum of the file as it ran is kept privately |
| `labeller/calibration_set.json` | `16e80cc6de916dbc1b26014ef344dcc5dbf530299963c94f2f5bd00c963dd4bc` | changed: prices, 45 literals (38 with a k suffix in the reply texts, quotes and review triggers; 7 expected price fields), and 1 size phrase (3 occurrences: reply text, quote and expected size field), freshly drawn, not computed from the old values; the checksum of the file as it ran is kept privately |
| `labeller/heldout_set.json` | `fddc7a6bff26f3c60b04481f901409ead3e23cea7768549aa691eb000094320b` | changed: prices, 33 literals (30 with a k suffix in the reply texts, quotes and review triggers; 3 expected price fields), and 1 percentage in a reply text, freshly drawn, not computed from the old values; the checksum of the file as it ran is kept privately |

This file (`RECORD.md`) is not listed in its own table.

**Note 1.** `labeller/labeller_request.json` names the system prompt and the schema by file ("contents of labeller_system_prompt.txt, unchanged"), with no checksum and no embedded copy. Nothing else in the published files pins the prompt or the two invented sets by checksum or embeds them. Published unchanged, the request therefore points at the published prompt; the runs used the prompt as it ran, whose checksum is kept privately.

**Note 2.** In `scoring/score.py`, every self-test result is unchanged: `python3 scoring/score.py selftest` gives 81 of 81, with output identical line for line to the file as it ran. In the three labeller files, for each of the 12 invented replies, the strict and loose labels that `combine.py` gives from the expected items are the same as from the files as they ran, and equal the expected labels; every expected quote is found in its reply. `python3 labeller/combine.py selftest`: 23 of 23 pass.
