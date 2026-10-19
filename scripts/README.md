# Pipeline

```
Legistar event id
  │  fetch_legistar.py              → legistar/ event.json, README.md, manifest.csv, attachments
  ▼
Council video page (EventVideoPath)
  │  fetch_media.py                 → <file>.mp4, <file>.vtt, media.json
  │  ffmpeg (inside fetch_media.py) → hearing-audio-64k.mp3 (transcribed), hearing-audio-16k.opus (published)
  ▼
Deepgram Nova-3, diarization on     → deepgram-intermediate.json  {segments:[{start,end,speaker,text,words:[{w,s,e}]}]}
  │  render_deepgram_raw.py         → <slug>-transcript-deepgram-raw.txt
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

Steps 1 to 3 (documents, media, transcription) and the last two steps have scripts. Speaker
naming and the clean verbatim edit are done by hand with AI assistance and are not scripted. The
full checklist for a new hearing, including the manual stages, is [`docs/PIPELINE.md`](../docs/PIPELINE.md).

Raw files live outside the repository, in a per-hearing folder (BetaNYC uses
`~/Movies/BetaNYC/council-hearings/<slug>/`). Below, `$D` is that folder.

## 1. fetch_legistar.py: the Council's documents

Python 3.11 to 3.14, standard library only. Needs a Legistar Web API token for client `nyc` in
`LEGISTAR_TOKEN` (NYC requires one; it is passed as the `token` URL parameter and never written
to disk). Network: `webapi.legistar.com` and Legistar's file hosts only.

```sh
python3 scripts/fetch_legistar.py 22795 --out "$D/legistar" [--out <copy>]
```

Calls `GET v1/nyc/Events/{id}?EventItems=1&AgendaNote=1&MinutesNote=1&EventItemAttachments=1`,
then `Matters/{id}` and `Matters/{id}/Attachments` for each agenda item
([reference](https://webapi.legistar.com/Help)). Writes `event.json` (the API responses),
`README.md` (event, agenda items, file table), `manifest.csv` (same columns as the published
`legistar/manifest.csv`) and every attachment plus the agenda PDF, named
`<matter-file>-<attachment-name>.<ext>`. The event record's `EventVideoPath` is the Council's
video page, which step 2 reads. Re-run after the hearing to pick up testimony and transcripts
the Council posts later.

## 2. fetch_media.py: video, captions, audio

Python 3.11 to 3.14, standard library only, plus `ffmpeg` and `ffprobe`. Network:
`councilnyc.viebit.com` and `vbfast-vod.viebit.com` only.

```sh
python3 scripts/fetch_media.py --event-json "$D/legistar/event.json" --out "$D"
```

Reads the Viebit page's embedded `pageConfig` (video id, original file name such as
`NYCC-PV-CH-CHA_261016-101016.mp4`, caption track), checks the MP4 beside the captions with a
one-byte range request, downloads the MP4 (resumable) and the Council's `.vtt`, then runs:

```sh
ffmpeg -y -v error -i <video>.mp4 -vn -ac 1 -ar 16000 -c:a libmp3lame -b:a 64k "$D/hearing-audio-64k.mp3"
ffmpeg -y -v error -i <video>.mp4 -vn -ac 1 -c:a libopus -b:a 16k "$D/hearing-audio-16k.opus"
```

and writes `media.json`: URLs, the ffmpeg commands and version, and bytes, duration and sha256
for every file. How the URLs were found is in the script's docstring.

## 3. Deepgram transcription

The Deepgram request is made by BetaNYC's private workspace script `scripts/deepgram_transcribe.py`
(Deepgram Python SDK; Nova-3 with `smart_format`, `punctuate`, `diarize` and `utterances` on), not
by code in this repository:

```sh
python deepgram_transcribe.py "$D/hearing-audio-64k.mp3" \
  --out "$D/deepgram-intermediate.json" --raw-out "$D/deepgram-response.json" \
  --keyterms-file hearings/<slug>/lexicon.txt --no-core
```

`--keyterms-file` sends the hearing's own keyterm list
([Deepgram keyterm prompting](https://developers.deepgram.com/docs/keyterm): Nova-3 only, at most
100 terms and 500 tokens); `--no-core` leaves out BetaNYC's organization list. See
[`lexicon/README.md`](../lexicon/README.md).

It writes Deepgram's response and the intermediate file
`{segments:[{start,end,speaker,text,words:[{w,s,e}]}]}`: one segment per Deepgram utterance,
`speaker` the utterance's voice cluster, `w` the punctuated word. Anyone without that script can
make the same request against the
[pre-recorded API](https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded)
and convert `results.utterances` the same way. Then, in this repository:

```sh
python3 scripts/render_deepgram_raw.py "$D/deepgram-intermediate.json" "$D/<slug>-transcript-deepgram-raw.txt"
```

writes `[HH:MM:SS] Speaker <cluster>: text`, one turn per paragraph, turns merged exactly as
`build_hearing.py` merges them, and prints segment, turn and cluster counts. Speaker naming
starts from this file.

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

The `--legistar-*` options rebuild `legistar/` from the pre-hearing download
(`--legistar-pre-dir`, a `fetch_legistar.py` folder read through its `manifest.csv`) and, when
there is one, the post-hearing re-download (`--legistar-post-dir`, same format). Where both have
the same file, the post-hearing copy wins, and a file whose size differs from its manifest stops
the build. The 2026-10-05 hearing was made from hand-made downloads, read with
`--legistar-pre-readme` (attachment table in its README) and `--legistar-post-json` (a JSON list
of `[matter, attachment, last_modified_utc, url, filename, bytes]`). Leave the options off to keep
the existing `legistar/` folder.

Re-running is safe: every output is rewritten in full, and the Opus file is copied only when
missing or a different size.

## validate_clean.py

Python 3.11 to 3.14, standard library only. No network access. Run after the clean verbatim
edit, before the build:

```sh
python3 scripts/validate_clean.py <unedited>.txt <clean>.txt --names
```

Exit 0 only when both files have the same number of turns and byte-identical
`[HH:MM:SS] Name:` prefixes. Also prints how many turns changed, the overall length ratio,
turns cut by more than 40%, and (with `--names`) every capitalized token added or removed.

## build_panels.py

Python 3.11 to 3.14, standard library only. No network access. For every hearing with a
`panels.json` (copied in by `build_hearing.py --panels`), writes `panels.html`, "Who spoke, panel
by panel": a timeline of every turn (panels as bands, one row per speaker grouped by category,
hover and keyboard focus for details, click or Enter to read a turn) and talk time per panel with
the Council, staff and witness split. The page is self-contained: no fonts, scripts or styles
from elsewhere.

```sh
python3 scripts/build_panels.py [--slug <slug>]
python3 scripts/build_hearing.py --index-only   # links the page from index.html and the hearing README
```

Category colors were checked with a colorblind-safety palette validator; every color is paired
with a written label and every value is in a table on the page.

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
  is dropped; hyphenated words are split; `join_terms` rewrites a few multi-word or variant
  spellings to one term before counting ("super intelligent" as "superintelligent"); a phrase may not start or end with a stopword (generic words, hearing boilerplate,
  and every token of every speaker name); grams containing "york"/"yorkers" and the bare word
  "city" are skipped;
- each group is scored against every other speaker with the weighted log-odds ratio and
  informative Dirichlet prior of Monroe, Colaresi and Quinn (2008), prior mass 1% of all phrase
  tokens; a phrase is kept when the group said it at least 3 times (2 for one person) with
  z > 1.96;
- a shorter phrase is dropped when a longer kept phrase contains it and has at least 80% of its
  count;
- a person is compared with everyone else at the hearing, including the rest of their group;
- beyond generic stopwords, filler was removed by hand after an AI assistant, at BetaNYC's
  direction, reviewed each group's and person's list. The pages say so, and link the list.

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

`test_fetch.py` checks the pure parts of steps 1 to 3 without network access: attachment
file names against the 2026-10-05 manifest, manifest columns, agenda-first ordering and
duplicate names, Viebit `pageConfig` parsing and host checks, the ffmpeg arguments, and turn
merging in the raw text.

`test_validate_clean.py` checks the clean-transcript validator: header skipping, prefix and turn-count
failures, shrink warnings and the `--names` report.

`test_panels.py` checks `build_panels.py` (talk-time sums, row order, band labels, every turn drawn
once in time order and keyboard-reachable, bars inside the plot, no external resources, links and
ids, idempotence), the `panels.json` checks in `build_hearing.py`, per-hearing word cloud configs, and
the built 2026-10-16 hearing.

`test_build.py` checks the 2026-10-05 hearing's built files: 830 turns, transcript prefixes, word timings inside
their turns, CSV columns and confidence values, WebVTT header and ordering, file sizes,
every relative link in `index.html`, and that speaker talk time sums to turn time.
