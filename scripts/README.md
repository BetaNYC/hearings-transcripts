# Pipeline

```
Council video (MP4)
  │  ffmpeg                         → hearing-audio-64k.mp3 (transcribed), hearing-audio-16k.opus (published)
  ▼
Deepgram Nova-3, diarization on     → deepgram-intermediate.json  {segments:[{start,end,speaker,text,words:[{w,s,e}]}]}
  ▼
Turns: merge consecutive segments with the same speaker cluster and a gap < 5 s
  ▼
Speaker naming                      → speaker-labels.json  [{i,name,role,confidence,evidence}], one per turn
  │  self-introductions, chair call-outs, the on-screen name banner (shown only for
  │  the Speaker), voice clusters; cross-checked against the Legistar roster, titles and
  │  bill sponsors and NYS Open Legislation member and sponsor records.
  │  Names were assigned by AI agents working from these sources, at BetaNYC's direction.
  │  Elected officials were checked against Legistar and NYS Open Legislation.
  │  Other names were not individually verified by a person.
  ▼
Transcript text                     → transcript.txt (unedited)
  ▼
Clean verbatim copy edit            → transcript-clean.txt
  │  AI-assisted: fillers, stutters and false starts removed; punctuation, spelling and
  │  number formatting fixed; words the transcription clearly misheard, including names,
  │  corrected. Speaker labels and timestamps unchanged (build_hearing.py enforces this).
  ▼
build_hearing.py                    → hearings/<slug>/… exports + index.html
  ▼
build_wordclouds.py                 → hearings/<slug>/wordclouds/… (then build_hearing.py --index-only)
```

Only the last two steps live in this repository. The steps above it produced the input files and
are described here so the outputs can be understood and reproduced.

Commands equivalent to the audio step (the exact invocation was not recorded; output formats
match the published files: MP3 64 kbps mono 16 kHz, Opus 16 kbps mono):

```sh
ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 -b:a 64k hearing-audio-64k.mp3
ffmpeg -i video.mp4 -vn -ac 1 -c:a libopus -b:a 16k hearing-audio-16k.opus
```

## build_hearing.py

Python 3.11 to 3.14, standard library only. No network access.

```sh
python3 scripts/build_hearing.py \
  --meta scripts/meta/2026-10-05-committee-of-the-whole-ai.json \
  --deepgram  <dir>/deepgram-intermediate.json \
  --labels    <dir>/speaker-labels.json \
  --transcript       <dir>/2026-10-05-committee-of-the-whole-transcript.txt \
  --transcript-clean <dir>/2026-10-05-committee-of-the-whole-transcript-clean.txt \
  --audio-opus <dir>/hearing-audio-16k.opus \
  --legistar-pre-readme <legistar>/README.md --legistar-pre-dir <legistar> \
  --legistar-post-json <post>.json --legistar-post-dir <legistar>/2026-10-06-post-hearing

python3 scripts/build_hearing.py --index-only     # rebuild index.html from hearings/*/
```

What it checks before writing, and refuses to continue if any fails:

- the merged turn count equals the number of speaker labels, and label `i` equals its position;
- every turn's `[HH:MM:SS]` prefix in both transcripts equals the computed turn start
  (whole seconds, truncated);
- every turn's speaker string in both transcripts equals the one derived from its label
  (`Speaker <name>`, `CM <name>`, `<name> (<organization>)`, plus ` [?]` for low confidence);
- every confidence is `high`, `medium` or `low`; every role has a category rule;
- no output file is 100 MB or larger (GitHub's per-file limit).

The `--legistar-*` options rebuild `legistar/` from the pre-hearing download (attachment table
in its README) and the post-hearing re-download (a JSON list of
`[matter, attachment, last_modified_utc, url, filename, bytes]`). Where both have the same file,
the post-hearing copy wins. Leave the options off to keep the existing `legistar/` folder.

Re-running is safe: every output is rewritten in full, and the Opus file is copied only when
missing or a different size.

## build_wordclouds.py

Python 3.11 to 3.14, standard library only. No network access. Reads
`hearings/<slug>/transcript/turns.csv`, `speakers.csv` and `hearing.json`, plus
`scripts/meta/wordclouds.json`, and writes `hearings/<slug>/wordclouds/`:

- `<group>.html` and `<group>.csv` for each group in the config;
- `people/<person>.html` and `.csv` for each person in the config;
- `index.html`, a gallery with each group's and person's top phrases.

```sh
python3 scripts/build_wordclouds.py            # every hearing with a turns.csv
python3 scripts/build_hearing.py --index-only  # adds the gallery link to index.html and the hearing README
```

Method, all parameters in `wordclouds.json`:

- phrases are 1 to 3 words from `text_clean`, never crossing `. ? ! ; : , ( )`; possessive `'s`
  is dropped; a phrase may not start or end with a stopword (generic words, hearing boilerplate,
  and every token of every speaker name); grams containing "york"/"yorkers" and the bare word
  "city" are skipped;
- each group is scored against every other speaker with the weighted log-odds ratio and
  informative Dirichlet prior of Monroe, Colaresi and Quinn (2008), prior mass 1% of all phrase
  tokens; a phrase is kept when the group said it at least 3 times (2 for one person) with
  z > 1.96;
- a shorter phrase is dropped when a longer kept phrase contains it and has at least 80% of its
  count;
- a person is compared with everyone else at the hearing, including the rest of their group.

Groups are defined by `match` rules on `speakers.csv`: `category`, `role_contains`,
`exclude_names`, `exclude_role_contains`. Pages lay the word cloud out in the browser (an
Archimedean spiral with bounding-box collision, measured with the page font after it loads,
shrinking all words together until every phrase fits). Re-running rewrites every output and
produces identical files.

## Tests

```sh
python3 -m unittest discover -s scripts -v
```

`test_wordclouds.py` checks that the six groups are non-empty and disjoint, that the council group
excludes the two chairs, that each group's and person's top 45 phrases equal the fixtures in
`tests/fixtures/wordclouds/` (regenerate them when `wordclouds.json` changes on purpose), that
"RAISE Act" forms as one phrase, that each person page counts only that person's turns, that every
page parses with six working group links, that all relative links resolve, and that the build
is idempotent.

`test_build.py` checks the built files: 830 turns, transcript prefixes, word timings inside
their turns, CSV columns and confidence values, WebVTT header and ordering, file sizes,
every relative link in `index.html`, and that speaker talk time sums to turn time.
