# NYC Council hearing transcripts

Open, speaker-labeled transcripts and data for New York City Council hearings, published by
[BetaNYC](https://beta.nyc/) so anyone can read, search, quote (after checking the video), and
build visualizations from what was said.

Browse and download: **https://betanyc.github.io/hearings-transcripts/** (or open `index.html`).

## Hearings

| Date | Body | Title | Folder |
|---|---|---|---|
| 2026-10-05 | Committee of the Whole | Oversight - Examining the Risks Posed by Artificial Intelligence | [`hearings/2026-10-05-committee-of-the-whole-ai/`](hearings/2026-10-05-committee-of-the-whole-ai/) |

BetaNYC's executive director, Noel Hidalgo, testified at this hearing; his testimony is transcribed and labeled the same way as everyone else's.

## Why

Council hearings are public, but the official transcript can take weeks to appear and the
video is hard to search. A timestamped, speaker-labeled transcript lets people find who said
what, jump to the moment in the video, and count who got the floor.

## What each hearing folder holds

| File | Format | Contents |
|---|---|---|
| `hearing.json` | JSON | Title, date, body, Legistar event id and URL, video links, duration, bills heard (file number, subject, lead sponsor), counts |
| `transcript/transcript.txt` | text | Unedited machine transcript, `[HH:MM:SS] Name: text`, one turn per paragraph |
| `transcript/transcript-clean.txt` | text | Clean verbatim edit of the same turns |
| `transcript/turns.csv`, `turns.json` | CSV, JSON | One row per speaker turn: `turn_id, start_sec, end_sec, start_hms, end_hms, speaker_name, speaker_role, confidence, deepgram_cluster, text_clean, text_unedited` |
| `transcript/words.json` | JSON | `[{turn_id, word, start, end}]`, every recognized word with its timing |
| `transcript/captions.vtt` | WebVTT | Captions with the speaker in a `<v>` tag; cues of 7 seconds or less, at most two lines |
| `speakers.csv` | CSV | `speaker_name, speaker_role, category, turns, talk_seconds, first_heard_hms` |
| `legistar/` | PDF, DOCX, CSV | The Council's documents for the hearing, plus `manifest.csv` (source URL and last-modified time for each) |
| `media/` | Opus, README | Small audio file; links to the video and the full-quality MP3 |
| `city-qa.html` | HTML | "What the City said": every question Council Members asked the administration's panel, with the full exchange from the transcript, the follow-ups the City promised and its position on each bill. Built by `scripts/build_qa.py` from `scripts/meta/<slug>-city-qa.json` |
| `wordclouds/` | HTML, CSV | "What each group talked about": a gallery (`index.html`), one page and CSV per speaker group, and `people/` pages for some individual speakers. Each CSV is `phrase, group_count, others_count, z` |

All times are seconds from the start of the Council's recording. Text is UTF-8.

### Speaker categories

`speakers.csv` adds a `category` derived from each speaker's role, so charts can group people.
The rule lives in `categorize()` in `scripts/build_hearing.py`, and the build fails on a role
it has no rule for.

| Category | Rule |
|---|---|
| `unidentified` | Role is `Unidentified`, or the name starts with `Unidentified` (applied first) |
| `council` | Role is `Speaker` or `Council Member` |
| `council-staff` | Role is `Committee Counsel` or `Sergeant-at-Arms` |
| `state-or-other-elected` | Role starts with `NY State Senator`, `NY State Assembly Member`, `NYC Public Advocate` or `UK Member of Parliament`, or is `Witness — NY State Senate` |
| `ai-company` | `Witness — OpenAI`, `Anthropic`, `Meta`, `Google`, or `company panel` (the AI company panel) |
| `city-official` | `Witness — OTI`, `NYC Cyber Command / OTI`, `DCWP`, `NYC Emergency Management`, `NYC Equal Employment Practices Commission` |
| `witness` | Any other `Witness — …` role: advocates, researchers, unions, other companies, members of the public |

Smaller AI startups that testified in the public portion (for example Babble AI, Trina AI)
are `witness`, not `ai-company`; `ai-company` means the four companies on the invited panel.

## How it was made

1. **Video to audio.** The Council's video was converted to audio with ffmpeg.
2. **Transcription.** Deepgram Nova-3 with speaker diarization. Diarization groups speech
   into voice clusters but does not know names.
3. **Turns.** Consecutive Deepgram segments with the same voice cluster and less than 5
   seconds between them are merged into one turn.
4. **Speaker names.** Assigned from self-introductions, the chair calling on people, the
   on-screen name banner (shown only for the Speaker), and voice clusters, then cross-checked
   against the Legistar roster, titles and bill sponsors and NYS Open Legislation member and
   sponsor records. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person. Each turn carries a confidence (`high`, `medium`, `low`).
5. **Clean verbatim.** An AI-assisted copy edit: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
   timestamp and speaker label match the unedited transcript exactly.
6. **Exports.** `scripts/build_hearing.py` (Python standard library only) writes every file
   above and `index.html`. See [`scripts/README.md`](scripts/README.md).
7. **Word clouds.** `scripts/build_wordclouds.py` scores the 1- to 3-word phrases in the clean
   transcript with a weighted log-odds test (Monroe, Colaresi and Quinn 2008, "Fightin' Words")
   to find what each speaker group, and some individual speakers, said far more than everyone
   else. Groups, people and word lists are in `scripts/meta/wordclouds.json`. Groups come from
   the AI-assigned speaker labels, so a mislabeled turn counts toward the wrong group.

## Known limits

- **This is a machine transcript, not an official record of the Council.** Words and speaker
  names can be wrong. Check the video at the timestamp before quoting anyone.
- `[?]` after a name in the transcripts (and `low` in `turns.csv`) marks a low-confidence
  speaker label. Some short turns are labeled Unidentified.
- Diarization occasionally puts two voices in one turn, typically a question and the first
  words of the answer. Talk time is approximate: a few turns contain two voices.
- Witness names are spelled as the transcription heard them and have not been checked against a witness list or written testimony. Some are likely misspelled; corrections are welcome as GitHub issues.
- Word timings in `words.json` and `captions.vtt` come from the unedited transcript. The
  clean edit has no word timings of its own.
- Each hearing's README lists its own gaps.

## License

- **Data** (transcripts, speaker labels, exports, page text): [CC BY 4.0](LICENSE-DATA),
  copyright BetaNYC 2026.
- **Code** (`scripts/`): [MIT](LICENSE).
- **Council material is not ours.** The hearing video and audio and the Legistar documents are
  public records produced by the New York City Council. They are reproduced here for
  convenience; BetaNYC's licenses cover only BetaNYC's work.

## How to cite

See [`CITATION.cff`](CITATION.cff). Short form:

> BetaNYC (2026). *NYC Council hearing transcripts*. https://github.com/BetaNYC/hearings-transcripts.
> Machine transcript; not an official Council record.

## Adding a hearing

Write `scripts/meta/<slug>.json` (copy the existing one), run the pipeline in
`scripts/README.md`, then run `python3 scripts/build_hearing.py …`,
`python3 scripts/build_wordclouds.py` (edit the groups and people in
`scripts/meta/wordclouds.json` first), `python3 scripts/build_hearing.py --index-only`, and
`python3 -m unittest discover -s scripts`. Files over 100 MB go to a GitHub Release, not git.
