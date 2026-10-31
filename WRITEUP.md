# Replaying an AI advisor: does the same model give the same weekly call?

A pre-registered experiment run in October 2026. Claude Sonnet 4.6 re-ran, through the API, the weekly check-ins of the advisor chats the author had used for a long-term investment plan (a first chat, then the one that took over from it). The question was whether the replays reproduced the advisor's calls.

**About this public version.** It gives aggregate results only. The conversations, the week-by-week calls, the dates of the check-ins, and everything about the author's plan, positions and accounts are kept private. The full record (registration, code, logs and reviews) is kept privately and is fixed by the checksums in section 10. Where this text quotes the private registration or rulings, "the user" means the author, and section numbers refer to the private registration.

## Summary

**Question.** Given the same weekly inputs the advisor chat had, does the same model (Claude Sonnet 4.6, served through the API in October 2026) reproduce the call the advisor made in each weekly check-in?

**Verdict: INCONCLUSIVE.** Over 17 weekly check-ins, with 5 replay samples each, the replays' most common call matched the advisor's call in **10 of 17 weeks (59%)** at the strict cut-off. A naive rule, "always NO CHANGE", matched 7. The registered pass mark needed at least 80% and a lead of at least 5.1 weeks over the best naive rule; the lead was 3. 40 of the 83 valid replays were written after the closing text (section 2.2): all 5 samples in 8 weeks, none in the other 9. The frozen scorer's verdict line:

`BRANCH: INCONCLUSIVE | score 10 of 17, bar 7 (rule c), margin 3; between 50% and 80%; a second extension is not run`

**Reading (ruled by the design chat, 21 Oct).** "Not shown under the strict headline", not "not reproducible". The misses are mostly split weeks, not consistent misses (7 of 8). The replays agree with each other about as often as they agree with the advisor (0.44 against 0.47). If the advisor's call were one more draw from its week's replays, the expected score would be 11.0 against the actual 10 (descriptive, with no verdict attached). On these numbers, the advisor's weekly call behaves like one draw from the same spread the replays draw from. Two live runs of the advisor on four overlapping weeks agreed on 0 of 4 at the strict cut-off (1 of 4 loose), so the 80% mark lies above what two live runs achieved. Those pairs did not share inputs, and four weeks is a small base.

**Cost and time.** $38.07 in API fees, against a pre-set cap of $70. Designed from 8 Oct 2026, frozen 18 Oct, verdict 21 Oct. Under the registered rules, INCONCLUSIVE counts like STOP for building purposes: the project closes with this finding.

## 1. Why this question

The author's long-term, staged buying plan in a highly volatile crypto asset was run with a Claude advisor chat: a framework set up in February 2026 and set out again when a new chat took over in April, then weekly check-ins, most of them on Claude Sonnet 4.6. In each, the advisor read the week's news and prices and recommended what to do with the plan's orders, price zones and reserve. Before thinking about automating any of it, the question was whether those calls were a stable function of the inputs, or partly chance and the particular conversation.

This is not a backtest and says nothing about returns. The registration reserved the question "did the calls make money?" for a separate registration, to be asked only after this verdict was written.

## 2. Design (registered before any scored call)

### 2.1 Reference set
- 28 weekly check-ins between February and September 2026: 9 in the first advisor chat and 19 in the chat that took over from it. The first chat also ran four more check-ins in parallel with the second chat's first four; those four are set aside as a yardstick (section 4.6).
- Scored weeks: the check-ins whose original ran on Sonnet 4.6 (documented in the chat for 10 of them, stated by the author for the rest; the data export does not record the model), less two that state no preferred option, and the yardstick weeks. **Run A:** 10 weeks of the second chat. **Extension:** 5 weeks of the first chat and 2 more of the second (7 weeks).
- Source: the two conversations from the author's data export, with thinking reduced to flags, built into a single source file by a script.

### 2.2 The replay
- **Model:** `claude-sonnet-4-6` through the Message Batches API, 5 samples per week, API default sampling, adaptive thinking where the original thought (from the second check-in of the second chat onward), `max_tokens` 16,000.
- **Context, as close to the app as could be rebuilt:**
  - Anthropic's published Sonnet 4.6 app system prompt (the 17 Feb 2026 version), with the check-in's date filled in;
  - the saved memory entries the advisor chat started with (the app's help page says memory edits apply to the next conversation, and the chat's start time confirmed that order);
  - the full conversation history up to the check-in, including attachments and earlier search results;
  - the author's name masked with a fixed pseudonym.
- **The week's research:** the advisor's own stored search results. The replay gets a search tool. Its first search returns all of that week's stored results under the advisor's original queries; further searches return "No further results are available."; a sample still searching at its fourth call is told, in the tool's voice, that searching is unavailable, and writes with the tool off. This closing rule was added after the form test (section 3.1).
- **Validity:** a sample is valid when it searched, its last call ends normally with at least 1,500 visible characters, and, on thinking weeks, it has a thinking block. Otherwise it is redrawn, at most twice, and then counted as failed. The rule reads only structure, never what a reply recommends.

### 2.3 Labelling
- Seven labels: BUY NOW, SELL NOW, LEAN IN (no trade now, but more buying or less selling), PULL BACK (the opposite), NO CHANGE, NO PREFERENCE (an open choice that would change the label), UNCLEAR.
- A labeller model (`claude-opus-5-5`, effort high, structured output) lists every recommendation item in a reply with its effect, object, strength (directive, proposed, floated), timing, condition, size, price and alternatives. A fixed script (`combine.py`, published here) turns the list into one label per cut-off.
- **Strict** (the headline) counts proposed and directive items; **loose** counts floated ones too. Deferred and conditional items never count, except a buy or sell to be done when a stated price is reached.
- Each reply is labelled alone, under a neutral ID, in two independent passes, with a third when they differ. Originals and replays are pooled and shuffled, and nothing in a request says which is which.
- Checked before any real reply: 8 invented calibration replies (0 misses of 16 labellings) and 4 held-out ones (0 of 8). The labeller prompt and both invented sets are published here, with their example prices and a few other invented details replaced (see `RECORD.md`).

### 2.4 Scoring (`score.py`, published here; frozen 10 Oct, re-frozen once on 14–15 Oct before any data)
- **Per week:** a hit when the original's label is the single most common label among the week's readable replays; ties share the credit (1/k). A week is excluded if the original is UNCLEAR, or if fewer than 3 valid or 3 readable replays remain.
- **The bar:** the best of three naive rules: (a) the previous numbered check-in's label, numbering across both chats (so the second chat's first check-in follows the first chat's last before the handover); (b) the most recent earlier reply with an item; (c) always NO CHANGE.
- **Order of checks (strict figures):** (1) labelling agreement at least 85% on the pool and 70% on replies with an action label, else NO DECISION; (2) no reply awaiting a third pass; (3) at least 8 scoreable weeks; (4) score at or below 50%: STOP; (5) one label on 80% or more of the originals: more weeks; (6) score at least 80% and a margin over the bar of at least max(3, 30% of scoreable weeks), also with doubtful weeks counted as hits for the rules: OPUS 4.6; (7) otherwise more weeks. "More weeks" after run A means the extension (all 17 weeks pooled); after the extension it reads INCONCLUSIVE.
- **Branches:** OPUS 4.6 would have replayed run A's 10 weeks with Opus 4.6, a different model of the same generation released before the replayed weeks, to separate the inputs from the model's habit.

### 2.5 Money, time and independence
- **Cap:** $70 for everything, enforced in code per batch against each batch's worst case; each step stops at twice its estimate.
- **Time boxes** per step, with a stop at twice the box.
- **Roles:**
  - a planning chat that had read the advisor's calls never designed labels or the pass mark;
  - a separate design chat (Claude Fable 5.1), blind to every reply, label and call, drafted the scoring rules and ruled on every later question touching a verdict or its reading;
  - a scoring chat that had not seen the calls settled the open scoring points and built `score.py`;
  - a build chat steered the build;
  - a builder agent (Claude Code under its own macOS user) wrote and ran the harness;
  - a validator agent (Claude Code under a second, read-only macOS user) reviewed the code and rebuilt every deciding number from the raw logs with its own code.
- **The paid door:** every paid call went through one command, only in a session the author started, after a go-ahead the author typed.
- **The freeze:** the harness, scorer, labeller, pinned inputs and registration were hashed before the first scored call, and every scored step refused to run if any of them had changed.

## 3. What happened

### 3.1 Before the freeze (12–18 Oct)
- **Build:** harness, tests (343 at the freeze), 21 validator reviews, including an open-ended review on a different model (Fable 5.1) and an inventory of unregistered decisions.
- **Form test** ($2.99):
  - The registered rule tried three forms in order: B (the model searches the stand-in itself), B-forced (the first call is forced to search), then A (the results placed in the conversation as if the search had already run). B came first and met its thresholds: it searched and thought in 5 of 5 samples. B-forced also passed; A, the last fallback, thought in only 1 of 5.
  - Two of five samples kept searching to the fourth call and gave no reply. A bare closing call with the tool off returned empty content in 3 of 3 cases.
  - A closing text in the tool's voice returned full replies in 3 of 3. The design chat ruled that closing rule, and it was registered before any scored call.
- **Cache measurement:** 0.909 of the input tokens of the registered measure (samples 2–5 of the form test, without the calls sent more than an hour after their step's previous batch) were read from the cache, above the 60% threshold, so caching stayed.
- **Labeller check:** 0 misses. **Dry run** on unscored weeks: passed.
- **Memory:** which saved memory entries the advisor received was settled from the app's documentation and the chat's start time. Later edits were kept as evidence and not sent. A phrase test found 0 of 20 phrases from the later entries in the advisor's later replies; the same method found 11 of 30 for the entries that were sent.
- **First freeze:** 18 Oct 14:57:57 UTC.

### 3.2 Run A (18 Oct)
- 50 of 50 samples valid; 1 resend (a sample that never searched); 30 of 50 samples (every sample of the last six weeks) searched to the limit and were closed with the closing text. $14.03.
- Labelling: 160 labellings, 4 third passes. The last batch was refused by an account-level spending limit; once the limit was raised, the batch was recorded as never created and its four requests sent again, with nothing sent twice. $4.65.
- **Score:** 7.5 of 10 strict (loose 6), bar 5 (rule c), margin 2.5 against 3 needed: **EXTENSION**. The validator's rebuild matched every figure.

### 3.3 The extension (19 Oct)
- 33 of 35 samples valid. One week lost 2 of 5 samples to the thinking rule: 9 of its 12 attempts had no thinking block, although every request asked for adaptive thinking. 10 samples closed (every sample of two weeks). $10.65.
- Labelling the 51 new replies (106 labellings, 4 third passes, $3.39) finished, then the manifest build stopped on a bug: the two failed samples had no reply, so no neutral ID, and the builder required one on every row. Run A had no failed sample, and no labelling-step test had one.

### 3.4 After the first freeze (19–21 Oct): one fix, one amendment, three reading rules
The fix, the amendment and the reading rules all came before the 17-week score existed; each was ruled by the design chat and recorded with its date in the registration.
- **The fix:**
  - **Ruling:** the bug sits after the replays and the labels, so the manifest and score are rebuilt whole from the logs.
  - **Change:** one condition in the manifest builder, plus tests that carry failed samples and an excluded week through to the report (369 tests after the fix). Nothing redrawn or relabelled.
  - **Checks:** the validator confirmed run A's manifest, score and report were byte-identical under the fixed code, and that the 17-week manifest held exactly the registered rows: run A's 78, the extension's 51 labelled replies, and two rows marked failed.
  - **Second freeze:** 20 Oct 16:22:41 UTC, with the first record kept unchanged. Its checksums were posted to the design chat before anyone built or scored the 17-week manifest.
- **The budget amendment** (proposed by the author, ruled 19 Oct): up to $30 more, usable only to complete the Opus branch. The estimates had assumed 3 in 10 samples would be closed; run A measured 30 of 50 and the extension 10 of 33, which put the Opus path at about $66–71 by the build chat's re-estimate, against the $70 stop. It was made before the extension's score existed and went unused.
- **The reading rules:**
  - the yardstick qualifier extends from STOP to INCONCLUSIVE;
  - the minimum-weeks and dominance checks apply to an Opus reading;
  - `score.py`'s printed report is the authoritative per-week table (it stays private, with the calls).
- **The author's spot check:** 20 of the 129 labelled replies were drawn with the registered seed, shown with neutral IDs, and marked before the score was computed (section 4.7).
- **The 17-week score:** computed on 21 Oct at 17:50 UTC from the logs (nothing sent, $0). The validator's independent rebuild gave a byte-identical manifest and score file and the same report figures, and passed it for acting on.

## 4. Results

### 4.1 The 17-week score (strict, the headline)

| | Strict | Loose |
|---|---|---|
| Scoreable weeks | 17 (none excluded; one week on 3 valid replays) | 17 |
| Score | **10 of 17 (59%)** | 8.5 of 17 (50%) |
| Naive rules (a), (b), (c) | 5, 4, 7 | 3, 3, 6 |
| Bar | 7 (rule c, always NO CHANGE) | 6 (rule c) |
| Margin over the bar (also with doubtful weeks as hits) | 3 | 2.5 |
| Margin needed | 5.1 | 5.1 |
| Wilson 95% interval (a floor) | 36% to 78% | 29% to 71% |
| Two-week block bootstrap, middle 90%: score / bar / margin | 6.5–13 / 4–10 / 0–6.5 | 5–11.5 / 3–8 / −1–6 |
| Dominance | NO CHANGE on 7 of 17 originals (not triggered) | LEAN IN 7 of 17 |
| **Verdict** | **INCONCLUSIVE** | (does not decide) |

Beside the headline: 40 of the 83 valid replays were written after the closing text, all 5 samples in 8 weeks, none in the other 9 (section 4.8). The bootstrap's two-week blocks pair scoreable weeks in list order, not by calendar, so the first chat's last scored week pairs with the second chat's first.

Run A alone, for reference: 7.5 of 10 strict (75%), bar 5, margin 2.5 against 3 needed; loose 6 of 10, bar 4.

### 4.2 Per week
The per-week tables stay private, since they carry the calls and the dates. Their flags, counted:
- **split:** the week's top replay label holds 60% or less of the valid replays: 12 of 17 weeks.
- **firm miss:** the top label holds 80% or more and is not the original's: 1 week, the one scored on 3 valid replays.
- **change week:** the bar's rule (always NO CHANGE) is wrong: 10 of 17 weeks.

### 4.3 Where the misses come from
- **Split, not wrong.** Of the 8 weeks scoring under 1, 7 are split and 1 is the firm miss.
- **The replays disagree with each other as much as with the advisor.** Share of replays matching the original: 0.47; share of replay pairs matching each other: 0.44. In run A alone: 0.62 and 0.48.
- **The original as a sixth draw.** If each week's original were one more draw from that week's replays, the expected score would be 11.0 of 17, beside the actual 10 (loose: 11.4 beside 8.5). The figure is descriptive, with no verdict attached: it is not a ceiling or a pass mark.
- **Change weeks.** In 10 of 17 weeks the advisor's call was something other than NO CHANGE; the replays matched 5 of those 10, and 5 of the 7 NO CHANGE weeks. Agreement was not carried by repeat weeks.

### 4.4 First chat against second chat
The first chat's 5 scored weeks matched 1.5 of 5; the second chat's 12 matched 8.5 of 12. The registration said higher agreement on the first chat's weeks would implicate a lost daily memory summary that only the second chat had, and called the comparison suggestive, not a test (the design chat's reading in section 5 calls it a partial test); the opposite was observed. The first chat's weeks also differ in other ways: thinking off, no memory entries, and three of five originals posing a choice through the app's widget.

### 4.5 The memory-gap weeks
The second chat's last two scored weeks lack memory edits made after the chat started (the app's documented behaviour). Without those two weeks: strict 9 of 15, bar 6, margin 3 (needed 4.5); loose 7.5 of 15, bar 5. Descriptive; the 17-week verdict stands.

### 4.6 The live yardstick
In the four overlap weeks, both live chats ran the same numbered check-in. Their labels matched in 0 of 4 pairs at the strict cut-off and 1 of 4 at the loose one.

The pairs did not share inputs: the first chat had its full history, the second the handover summary and memory entries, so their agreement measures robustness to how the context was compressed. Two more facts temper the figure. Only one pair ran on the same day; the others were 4 to 8 days apart, with different prices and possibly a changed plan state in between. And the author recalls the two chats' guidance matching in at least two of these weeks, in different words. In the pair that matches at the loose cut-off, the labeller's three passes read one chat's move three ways (absent, proposed, floated), so it counts only at the loose cut-off: there the labels differ on firmness, not on direction, which would fit that memory. The recollection is recorded as a caveat on label-level measures, not as data.

### 4.7 Labelling and the spot check
- **Labeller agreement**, two passes on the same reply:
  - pool: 123 of 129 strict (95%); replies with an action label 63 of 69 (91%);
  - replays only: 79 of 83 (95%) and 45 of 49 (92%).
  - Both gates pass; 8 third passes, all settled; no three-way split.
- **Strict labels across the 129 pooled replies** (originals, replays and context replies together): NO CHANGE 63, LEAN IN 43, NO PREFERENCE 11, BUY NOW 6, PULL BACK 5, UNCLEAR 1.
- **The author's spot check:** 14 of 20 agree, 6 disagree.
  - **Where:** the disagreements were 5 replays and 1 context reply, none of them an original.
  - **On what:** by the author's own reasons, 4 of the 6 turn on how an open choice is labelled (the NO PREFERENCE boundary); the other 2 turn on actions put off or made conditional.
  - **The labeller:** its first two passes gave the same strict label on all 6 (5 of 6 at both cut-offs; one reply's loose labels differed and went to a third pass).
- **How to read the gap:** the labeller agreed with itself on all six at the cut-off the author marked; the author's reasons turn on points of the labelling rules, recorded without judging who is right. The author could tell originals from replays while marking, a limit registered in advance. By registration, a disagreement is reported as a disagreement, never as a labeller error.

### 4.8 Validity, closing and cost
- **Samples:** 85 replay samples over 17 weeks; 83 valid, 2 failed, 8 resends.
- **Closed samples:** 40 of the 83 valid replays were written after the closing text: all 5 samples in 8 weeks, none elsewhere. Run A's closed weeks scored 4.5 of 6 against 3 of 4 for its open weeks; no pattern on these numbers.
- **Length:** the 25 originals in the labelling pool ran 4,627 to 9,788 visible characters, counted as the labeller sees them; the extension's 33 kept replays ran 6,220 to 12,254 in their last call (6,220 to 12,301 over all calls).
- **Spend:** checks and form test $5.35; run A $14.03; its labelling $4.65; the extension $10.65; its labelling $3.39. **Total $38.07 of $70**; the Opus reserve was not used.

## 5. Reading (ruled by the design chat, 21 Oct; reproduced as given, except one pronoun)

In these quotes, "the user" is the author, the section numbers are the private registration's, and "OLD" and "NEW" are the first and second chats. One pronoun is replaced in square brackets.

> The experiment ends INCONCLUSIVE: 10 of 17 weeks matched under the strict headline against a bar of 7 from 'always NO CHANGE', a margin of 3 where 5.1 was needed. The result reads 'not shown under the strict headline', not 'not reproducible'. Three registered readings qualify it. Where the misses come from: of the 8 weeks scoring under 1, 7 are split weeks and 1 is a firm miss; 12 of 17 weeks are split. The replays were not consistently somewhere else: they were spread. By the registered 2×2, this points to instability of the model's own output on these inputs rather than to lost context, serving drift or the model's habit, which would show as firm misses. The original as one more draw: replays agreed with each other on 0.44 of pairs and with the original on 0.47; had each original been a sixth draw from its week's replay distribution, the expected score would have been 11.0 against the actual 10. On these numbers the advisor's call behaves like one draw from the same distribution the replays draw from. The headline measures whether the mode of five reproduces one draw; it does not measure whether the distribution was reproduced, and the sixth-draw line says that it may have been. The live ceiling: the yardstick pairs, two live runs on the same four weeks, agreed on 0 of 4 strict and 1 of 4 loose, so the 80% mark lies above what two live runs achieved, and the result reads 'below the live ceiling'. Section 14's caveat holds: the pairs did not share inputs, so this is a ceiling for a different comparison, and four weeks is a small base. What does not qualify it: labelling agreement passed both gates; dominance was not triggered; change weeks matched 5 of 10 against 5 of 7 for the others, so agreement was not carried by repeat weeks. The user's spot check agreed on 14 of 20, with 4 of the 6 disagreements on the NO PREFERENCE boundary; the user could tell originals from replays, as section 12 anticipated. [The user's] recollection that the live chats' guidance matched in at least two overlap weeks whose labels differ is recorded as a caveat on label-level measures, not as data. The loose cut-off (8.5 of 17, bar 6) does not change any of this.

> Section 6.1 registered one partial test of the lost daily memory summary: higher agreement on the OLD weeks, which never had it, would implicate its loss. The opposite was observed: OLD #3–#6 and #9 matched 1.5 of 5, NEW #10–#21 8.5 of 12. The registered test therefore did not fire, and the summary's loss is not implicated by it. The comparison cannot clear the gap either: the OLD weeks also ran with thinking off, with no memory entries at all, with three of five originals posing a choice through the app's widget, and on five weeks. Any of these could account for the difference. The direction of the lost summary's effect remains unknown, as registered.

> Replays written after the closing text, 40 of 83, sit in 8 weeks that scored 4.5 of 6 in run A's closed weeks against 3 of 4 in its open weeks; no pattern on these numbers.

## 6. Limits

### 6.1 Accepted gaps, registered before the runs
- The lost daily memory summary of the second chat's first months, the largest; its direction is unknown.
- The app's unpublished tool instructions and definitions.
- Earlier thinking, which the export does not keep.
- Whether the app kept every earlier search result in context.
- The app's thinking budget, sampling settings and the default effort of adaptive thinking.
- Whether the app ran an unpublished variant of the published system prompt.
- Memory edits after the second chat started, not sent to its last two scored weeks.
- The model of the extension weeks, which rests on the author's statement.
- The search stand-in: further searches return nothing new, and closed samples write after a closing text the advisor never saw. A closed sample redrawn for length would over-represent samples that stopped searching on their own; none was redrawn.
- The app's choice widget, which no replay can use.

Known deviation, reported and not fixed: the advisor saw the author's real name; the replays and the labeller saw the pseudonym.

### 6.2 Biases toward agreement, the counterweight
- The history carries the advisor's own earlier calls and the author's reactions to them.
- The search results show the advisor's original queries.
- The registered third bias, the advisor's preamble inserted verbatim under form A, did not arise for the week being replayed, since form B was used. The history does write earlier weeks in A's shape, so the advisor's earlier preambles appear there verbatim.

Everything else biases against agreement.

### 6.3 What the design cannot separate
- **Same weights, different serving stack:** the API in October is not the app that served the original weeks (March to July).
- **Conditional on the true history:** each replay is conditional on the real history, including the advisor's real earlier calls, so the result does not say whether a fresh run of the whole series would end in the same place.
- **No ceiling:** there is no positive control; replay-to-replay agreement measures consistency, not a ceiling.
- **The labeller:** it was validated on invented replies, and it may know how the weeks turned out. That exposure is symmetric between originals and replays. Sonnet 4.6 and Opus 4.6 were released in February 2026, before the replayed weeks, so the replays themselves cannot know.
- **A second implementation, not a second judgment:** the validator rebuilt every deciding number with its own code, but it reviewed `score.py` before writing its own scorer, and only for the later rebuilds wrote its code from the record before reading the builder's. It ran on the builder's model (Opus 5.5) for its first ten reviews and on Fable 5.1 for the next two. Because a download bug found in the form test had passed the earlier same-model reviews, an open-ended review of the whole harness on Fable 5.1 was run before the freeze.

### 6.4 Observed in the results
- **The label scheme splits hairs.** Seven labels with a strict and a loose cut-off draw fine lines, and with five samples a week one sample crossing a line can move a week's top label; the NO PREFERENCE boundary carries most of the author's disagreements. Whether a coarser call would agree more is the first follow-up (section 9).
- **One week is thin.** It rests on 3 valid replays; its thinking failures were the model's own (every request carried the thinking setting).
- **The yardstick is loose.** Three of its four pairs were days apart.

### 6.5 Small deviations and notes (none changes a figure)
- **Neutral IDs:** the registration says each labelling step's IDs leave out those used by earlier steps. The harness left out run A's IDs for the extension, but not the dry run's 8, so run A's pool reused all 8; none recurred in the extension's pool. An ID's number carries no information either way.
- **Tie-breaks:** the generated report counts tie-breaks over labellings, not over final labels.
- **A recorded $70 cap that the code never read:** the step list carried it as documentation; the code enforced the total elsewhere.
- **The failed samples' counts:** the generated report's table prints search and call counts over all 5 samples of the thin week, the failed samples' last attempts included.
- **Rounding:** the five step figures sum to $38.067454 against the book's $38.067456.

## 7. What the result does and does not show
- **It does not show** that the advisor's calls were unreproducible, nor that they were model-specific. The Opus branch was not reached, so the model's role is untested.
- **What it suggests**, in the design chat's words: "On these numbers the advisor's call behaves like one draw from the same distribution the replays draw from. The headline measures whether the mode of five reproduces one draw; it does not measure whether the distribution was reproduced, and the sixth-draw line says that it may have been." The replays agree with each other (0.44 of pairs) about as often as with the original (0.47).
- **It says nothing about returns.**
- **For building:** the registration says of INCONCLUSIVE: "For building purposes it counts like `STOP`"; and of STOP: "For building purposes the project closes with that finding". The build chat's reading: this result gives no support for automating the advisor role as it was run, one discretionary call per week. A system that samples several answers on a fixed research packet, and acts only when they agree, would be a different design, to be tested on its own.

## 8. Lessons on method
- **Measure the model's own spread before setting a pass mark.** The replays agreed with each other on 0.44 of pairs; an unscored pilot on weeks outside the scored set could have measured that spread before the 80% mark was set.
- **Test every outcome a registered rule can produce, through to the report, before the freeze.** The failed-sample crash passed 343 tests because no labelling-step test had a failed sample.
- **Check the app's documented behaviour before building on it.** The memory question took two rulings and three rewrites until one help-page sentence settled it.
- **Quote registered text and rulings; don't paraphrase them.** The first draft of the private write-up drifted from the registration in three places, each toward a tidier result; the validator caught all three.
- **What made the result trustworthy:** a blind design authority; a read-only validator rebuilding every deciding number from the logs with its own code (a second implementation, not an independent judgment: section 6.3); a paid door with a typed go-ahead; and a freeze that every scored step checks.

## 9. Follow-ups (each a separate registration; none changes this verdict)
Costs are rough estimates.

- **A coarse relabelling** of the same 129 replies (buy / hold / sell / move an order), to see how much of the splitting came from the fine scheme. About $4.
- **A research-packet pilot** without a search tool, on two weeks, to see whether the search loops changed the answers. About $3.
- **A search-topic analysis** of what the advisor searched for, week by week, and whether the replays asked for the same things. Offline, $0.
- **The Opus branch**, under a dated note written before spending, if the question of the model's own habit matters. About $28.

## 10. Records
The private record is kept unchanged. These checksums fix it, so that it can be shown later that nothing in it moved after the result:
- **First freeze record:** SHA-256 `038650091f6b7fb36bb9e62d2fc08937893cfe4088661d1989bd10c419109f8d` (registration as frozen: `14d4b8e5c425442d8d06be33535222dd650ea202c00704fabd89112e9f4368a9`).
- **Second freeze record:** SHA-256 `d6e4b930c12906f11caee751489923e5b9836b2793ae47c0a66ef2f392b41648` (registration: `2a1def6aed26e245bc3ad6979ca7c56474c09b7687187139888e49961c34ae3b`).
- **Registration with the result entry:** `8b9890caf6957ab461c2bc88efa1f2822886be4f72f04a53cb211dd5f706d862`.
- **The 17-week manifest:** `86593664f3b4404609bd2ba23c1a9b0f40977c9863549eb124f608bd65141390`; its score file: `5a347865b3ec474fd47f8b84ca870ab25963684db9c43d1d61c23e110d14cc07`.
- **The frozen scorer and labeller files:** their checksums stay in the private record and are not published. The published copies differ from them only in invented dates, prices and a few sizes, and a published checksum would let anyone test guesses of the originals.
- **The published files** and how each relates to the frozen file it comes from: `RECORD.md`.
- **Validator reviews:** the private write-up this text is derived from was checked twice (one review failed it on wording, the corrected version passed), and this public copy was checked by the validator before publication.
