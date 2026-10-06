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
```

Only the last step lives in this repository. The steps above it produced the input files and
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

## Tests

```sh
python3 -m unittest discover -s scripts -v
```

`test_build.py` checks the built files: 830 turns, transcript prefixes, word timings inside
their turns, CSV columns and confidence values, WebVTT header and ordering, file sizes,
every relative link in `index.html`, and that speaker talk time sums to turn time.
