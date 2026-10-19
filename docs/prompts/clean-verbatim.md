# Prompt template: clean verbatim (stage 5)

Used to copy-edit the named transcript with AI agents, one agent per part. Adapted from the
prompts used for the 2026-10-05 hearing (the originals are kept in the operator's private workspace). Check every result with `scripts/validate_clean.py`.

Fill every `{{…}}` placeholder from the hearing's own sources (Legistar roster, committee report,
captions). Never fill one from memory.

---

You are copy-editing part {{N}} of {{PARTS}} of a machine transcript (Deepgram) of the NYC Council
{{BODY}} hearing "{{TITLE}}", {{DATE}}. Operator: {{OPERATOR}}, machine: {{MACHINE}}. Only read and
write local files; no web or API calls. Do not use bare `ls` (it hangs here); use /bin/ls, find or
Python.

INPUT: {{INPUT_PATH}}. Turns are separated by one blank line. Each turn starts with a prefix
`[HH:MM:SS] Name: ` followed by the spoken text.
OUTPUT: {{OUTPUT_PATH}}, same format.

Do a "clean verbatim" edit. This will be published as a public dataset, so faithfulness matters
more than polish.
DO:
- Remove filler words and verbal tics (um, uh, "you know" and "like" when they are filler),
  stutters and repeated words ("I I", "the the"), and abandoned false starts (keep the finished
  thought).
- Fix punctuation, capitalization and sentence breaks. Use American spelling.
- Fix clear mis-hearings of proper nouns and terms when context makes the right word certain:
  {{TERMS, e.g. organizations, products, laws and bill numbers in this hearing}}. Council Member
  names follow the Legistar roster: {{ROSTER}}. Witness names: {{WITNESS_SPELLINGS with their source}}.
- Spell numbers the way a court reporter would ("$1.5 billion", "120 children", "2025").
DO NOT:
- Paraphrase, summarize, reorder, or "improve" anyone's wording or grammar beyond the above.
  Keep their word choices, including informal ones (be consistent if you expand "gonna").
- Change a word that changes the meaning unless the Council's captions at {{CAPTIONS_PATH}} and
  the transcript context both support it. A plausible-sounding fix is not a fix.
- Drop any substantive content, interruptions, or crosstalk that carries meaning ("Yes." and
  "No." answers must stay).
- Change, merge, split, add or remove turns, or touch the `[HH:MM:SS] Name: ` prefix in any
  way, not even names that look wrong. Keep `[?]` markers.
- Guess at a word you cannot recover. Use [inaudible] only where the text is clearly garbage;
  otherwise leave the original words.

Work through the whole file in chunks so you don't lose turns. When done, run:
  python3 -I scripts/validate_clean.py {{INPUT_PATH}} {{OUTPUT_PATH}} --names
It must exit 0 (same turn count, identical prefixes). A length_ratio around 0.85 to 0.97 is
normal; investigate any "shrunk >40%" turns and restore content if you over-cut. Fix and re-run
until clean.

Reply briefly: the validator output line, and a list of the proper-noun corrections you made
(old → new, with count), plus any you were unsure about and left alone.

---

After the agents finish: merge the parts, run the validator on the whole file with `--names`,
and check every meaning-changing edit against the captions (see `docs/PIPELINE.md`, stage 5).
