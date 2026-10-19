# Prompt template: speaker naming (stage 4)

Used to label speakers with AI agents, one agent per chunk of the raw transcript (about 2.5
hours of video per chunk). Adapted from the prompts used for the 2026-10-05 hearing (the originals are kept in the operator's private workspace). The `MIXED:` note was added for the 2026-10-16 hearing.

Fill every `{{…}}` placeholder from the hearing's own sources: the Legistar roster (OfficeRecords),
the committee report, `panels.json` if it is already drafted, and the Council's `.vtt` captions.
Never fill one from memory. Prepare the input first: one line per turn,
`#<i> [HH:MM:SS] S<n>: text`, built from `deepgram-intermediate.json` with the same merge rule as
`build_hearing.py` (`render_deepgram_raw.py` writes the same turns), plus any evidence notes such as
`(BANNER: <name>)` from on-screen name banners or Zoom labels read from video frames.

---

You are labeling speakers in a machine transcript of the NYC Council {{BODY}} hearing
"{{TITLE}}", held {{DATE}} ({{DURATION}}, video time). Operator: {{OPERATOR}}, machine: {{MACHINE}}.
You only read and write files; do not call any web service or API.

INPUT: {{CHUNK_PATH}}{{CHUNK_NOTE, e.g. " (video time 2:30 to 5:00; it starts mid-hearing)"}}. Each
turn looks like `#<i> [HH:MM:SS] S<n>: text`. `S<n>` is Deepgram's voice cluster id. It is
UNRELIABLE: one id can cover several different people, and one person can be split across ids.
{{EVIDENCE_NOTES, e.g. "A note `(BANNER: Julie Menin)` means the on-screen name banner showed Speaker Julie Menin during that turn (strong evidence)."}}

TASK: give every turn number in your file a speaker name. Read the whole file in order. Use
evidence from the text: people introducing themselves ("My name is…", "I'm councilmember…"),
the chair calling on someone, answers following a named question, oath or affirmation
responses, panel roll calls, and continuity (a turn that obviously continues the previous
speaker's sentence is the same person). Transcription garbles names: {{KNOWN_GARBLES, e.g.
"Menon/Manon/Manning" = Julie Menin}}. When the transcript and a name disagree, the Council's
captions at {{CAPTIONS_PATH}} are a second source; quote them in the evidence.

Context:
- {{CHAIRS, e.g. "Speaker Julie Menin and Chair Carmen De La Rosa ran the hearing."}} Committee
  counsel and staff read the oath and call witnesses: label them "Committee Counsel" unless named.
  The opening decorum announcement is the Sergeant-at-Arms.
- Council Member roster (use these spellings): {{ROSTER from Legistar OfficeRecords}}.
- Witnesses and parts of the hearing: {{WITNESSES and PANELS from the committee report, panels.json and the captions}}.
  Get each witness's organization from the text.

RULES:
- Never guess. If you cannot tell who a council member is, use "Unidentified Council Member";
  for a witness, "Unidentified Witness"; otherwise "Unidentified". A wrong name is worse than
  "Unidentified".
- Fix name spellings only when the roster, the captions or a clear self-introduction supports it.
- If a turn holds more than one voice (a question and the start of its answer, for example),
  label it with the person who speaks most of it and start the evidence with
  `MIXED: <who says what> (~HH:MM:SS)`. Do not split turns.
- Do not use bare `ls` (it hangs on this machine); use /bin/ls, find, or Python.

OUTPUT: write a JSON array to {{OUTPUT_PATH}}, one object per turn in your file, in order:
{"i": <turn number>, "name": "Julie Menin", "role": "Speaker" | "Council Member" | "Committee Counsel" | "Sergeant-at-Arms" | "Witness — <organization or 'public'>" | "Unidentified", "confidence": "high" | "medium" | "low", "evidence": "<short reason>"}
Then validate it with Python: it must parse, and its set of "i" values must equal the set of
turn numbers in the input file. Reply with: count of turns labeled, count by confidence, a list
of the distinct names you used with their roles, and anything you were unsure about. Keep the
reply short.

---

After the agents finish: merge the chunks into `speaker-labels.json` (one entry per turn, `i`
equal to its position), cross-check voice clusters against the names, check every elected
official against Legistar, and write the named transcript. A role must have a category rule in
`build_hearing.py` (`categorize()`); a new organization that is an invited AI company needs to be
added to `AI_COMPANY_ORGS` on purpose.
