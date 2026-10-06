# Word cloud fixtures

The top 45 phrases (with `group_count`, `others_count`, `z`) for each group, and in `people/`
for each person, as built by `scripts/build_wordclouds.py` from `scripts/meta/wordclouds.json`.
`scripts/test_wordclouds.py` requires the build to reproduce them exactly.

**The contract is the meta file, not the prototype.** The first version of these fixtures was
the approved prototype's output (`distinct.py`, 2026-10-06), and the build matched it exactly.
The same day, filler words were added to the stopwords (for example "first", "exactly", "sir",
"ma'am", "fundamentally"); "act" moved from the stopwords to `skip_exact_grams`, so "RAISE Act"
forms as a phrase while a bare "act" is still skipped; and "space" was dropped as filler.
The fixtures were then regenerated from the new build.

After QA the same evening: topical words cut too eagerly were restored ("third", "deal",
"bet", "seat", "plan", "goals", "maintain", "industry", "labs", "results", "intelligent").
Hyphenated words are now split ("self-improvement" counts as "self improvement"), and
`method.join_terms` counts a few variant spellings as one term ("super intelligent" as
"superintelligent", "kill switch(es)", "open-weight", "affected parties"). A bare "third", "party" or "parties" is skipped like "act" (the multi-word forms still count).
Then "standing", "hundred", "spent" and "gets" were added as filler that the changes
surfaced. Fixtures were regenerated again.

When you change `wordclouds.json` on purpose, review the new phrase lists, then regenerate
these fixtures and say so in the commit.
