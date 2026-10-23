# Case study: building a research copilot you can check

## The problem

Ask a language model about a stock and it answers fluently and with confidence. For research, that is the dangerous part:
a wrong number with a citation next to it looks exactly like a right one. I wanted an assistant whose answers I could check
in under a minute, and whose failures were visible instead of smooth.

Citewise for Markets answers questions about public companies from four kinds of stored data: SEC filings, daily prices,
financial figures worked out from the filings, and news headlines. It runs on one PC with a local model. This is the story of
how I made it trustworthy, and, just as much, how I measured how far it got. (The [README](../README.md) has the overview.
[DECISIONS.md](DECISIONS.md) has every entry in full, including the ones that make me look bad.)

## Five rules, each from something that went wrong

1. **A citation does not prove a number.** An early answer said Microsoft's revenue grew "$49.9 billion", with a valid
   citation. The filing says $50.1 billion. The cited passage was a table with no growth figure in it, so the model had done
   its own subtraction, wrongly. Now every figure in an answer must appear in the passages it cites. If one does not, the
   model gets one retry, then the answer is shown with a visible warning.
2. **Right digits can still tell the wrong story.** Asked "Why did Nvidia stock fall this month?", the model wrote "fell by
   -3.68%". The stock had risen 3.68%. The digits matched, so the numbers check passed. Now Python writes the direction in
   words into the source ("a rise"), and code checks the direction and any minus sign in the answer.
3. **The model quotes; Python computes.** Every price change, high and low, 52-week range, trailing-twelve-month figure,
   margin, and P/E comes from Python, worked out from raw figures stored from the SEC. Each carries its recipe and its source
   filings. The model never does arithmetic.
4. **Warnings are attached by code, never left to the model.** Alphabet's P/E looks cheap because of investment gains. In
   the first real test, the model's own sentence left that caution out. Cautions now travel with the figures they concern and
   are attached to the answer in code.
5. **Headlines are context, never a cause.** They are titles only, so they cannot show why a price moved. Telling the model so in
   the prompt did not stop it hedging ("may have influenced market sentiment"), so the code checks for it, retries once, and
   shows a caution if it persists.

## Measuring it honestly

My early evaluation sets scored about 97%. That told me very little, because I had adjusted the rules to pass those exact
questions. So each later round used questions written in new wording, written before anything was run, run once, with every
answer read, including the passing ones:

| Round | Score |
|---|---|
| First fresh round (36 cases) | 78 of 108 (72%) |
| Second (35 cases, after fixing the first round's failures) | 68 of 105 (65%) |
| A third, deliberately harder | 48 of 105 (46%), about 60% after reading every answer |
| Sealed rounds 3 to 5, keywords only | 58%, 66%, 65% |
| Sealed rounds 3 to 5, with a local-model router | 70%, 79%, 78% |

Each fix repaired its own phrasings and little beyond them: new everyday wording missed in the same places. And the worst
failures were not refusals. They were confident wrong answers: three headlines that existed nowhere in the stored data, "no
price data" when prices were stored, "over the past ninety days" answered with one month's data, a missed "this is not
advice" notice for "is it time to cash out of Nvidia?", and "Google doubled this month" accepted as true when it had risen
about 1%. Those became the targets, because a refusal costs a reader a minute and a confident wrong answer can cost more.

## Two experiments that taught me more than the wins

**Asking the model to route questions.** Which kind of data a question needs was decided by keyword rules, and each new
round found new wordings they missed. On 39 fresh questions the keywords passed only 44% of checks (52 of 117), and 17
of the 21 first-pass misses never reached the right data at all. So I let the local model answer one constrained question (a JSON schema: does this
need prices, news, figures, filings?), only when the keywords found nothing, and only ever to add to the keyword route. The
first version looked even with the keywords overall (755 of 846 each) but won 9 cases and lost 8, because it overrode routes
the keywords send to the filings on purpose: for "Apple's iPhone sales" the keywords were right in 12 of 12 runs and the router
in 0 of 12. I fixed that with guards in code, each with a question of its own. On a sealed set run once, it then scored 93 of 114
against the keywords' 78. The score had hidden a problem I only found by reading the answers: its "outside" verdict had wrongly
declined 13 of about 38 ordinary research questions that name no tracked company. I made that verdict a hint that never stops a search. The final
sealed score was 90 of 114 (79%) against 78 (68%).

**Letting the model second-guess the keywords.** I replayed 302 cases three times through five policies. Where the router and
the keywords disagreed, the router was right 10 times and the keywords 58. All 10 router wins were cases I had written to
expose a keyword mistake. No policy beat the current one on the older cases, so I did not build it.

## Things I tried and dropped

- **Rebuilding financial tables as readable rows** for the model. It never changed or lost a number, but it did not fix the
  question: asked for "last quarter", the model picked the last month's row 0 times in 5 with or without the rebuild, and one
  answer said "26,223 million shares" for a figure stated in thousands. The model could see the Total row; it read "last quarter" as
  "the latest period listed". That is a problem of understanding, not layout, so I kept only the smaller fix: about 30% of table
  passages (420 of 1,479) had lost the sentence stating their units to the cut between passages, so the code now puts it back
  when the prompt is built.
- **Showing the router the previous question** so "do the same for Google" has a topic. No better (80 of 117), so I removed it.
- **Editing the shared prompt.** Three small wording edits moved "should I sell" from 16 of 20 to 4 of 20. New behavior now goes
  in a conditional block, never in the shared prompt.

## When more of the same stopped helping

Across the last three sealed rounds the router-on score was 70%, 79% and 78%. My agreed stopping rule was 85 to 90 percent twice
in a row; it was not met, and after reading every answer I put the honest range at 78% strict to about 85% generous. I expected
each further round of keyword fixes to buy about one case. So I stopped writing word lists and added a local log of my own real questions. Its first
real finding was something no synthetic round had caught: "hows nvda doing" was refused, because a lowercase ticker was not a
company and "hows" was not "how's".

## The rest of the engineering

- **A silent failure, found by reading one answer.** An answer quoted "the latest close" a day old, while the nightly job reported
  "success, 0 problems". At 5pm the just-finished day was missing from Yahoo's response, so I moved the job to 3pm and checked
  the next run. I recorded that this is one run and that the cause is not proven.
- **Backups count only after they are restored** into a temporary database and every table's row count matches.
- **Tests that can fail.** For the question log I deliberately broke the code 83 ways; one went uncaught, and it was an equivalent
  mutant. Later, running everything on a clean machine with an empty database found four tests that passed only because of what
  was in my own database, and CI now catches that kind of fault.
- **Generated types, CI, pinned dependencies, and a linter**, so the web screens cannot drift from the API and a fresh install
  behaves like mine.

## Limits, and what I would do next

The evaluations are small, judged by one reviewer, and the person writing the questions had read the rules. Numbers from different
rounds are not the same bar, and the sealed sets are spent once run. The model is a local 8-billion-parameter one; filings and
figures cover US filers only; the free price and headline sources are not licensed for a public product.

Next, in the order the failures point: review the real-question log for confident wrong answers rather than adding more word
lists; store share repurchases by period as a computed figure the model only quotes (the table rows are the model's weakest spot);
and try a stronger model behind the same interface once cost allows. The answers I trust most are the ones where a reader can
check each claim against its source, and every change above was meant to make that easier.
