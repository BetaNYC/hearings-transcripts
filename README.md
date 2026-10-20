# NYC Council hearing transcripts

Open, speaker-labeled transcripts and data for New York City Council hearings, published by
[BetaNYC](https://beta.nyc/) so anyone can read, search, quote (after checking the video), and
build visualizations from what was said.

Browse and download: **https://betanyc.github.io/hearings-transcripts/** (or open `index.html`).

## Hearings

| Date | Body | Title | Folder |
|---|---|---|---|
| 2026-10-16 | Committee on Technology | Oversight - Continuing Discussion about the Risks Posed by Artificial Intelligence | [`hearings/2026-10-16-technology-ai/`](hearings/2026-10-16-technology-ai/) |
| 2026-10-05 | Committee of the Whole | Oversight - Examining the Risks Posed by Artificial Intelligence | [`hearings/2026-10-05-committee-of-the-whole-ai/`](hearings/2026-10-05-committee-of-the-whole-ai/) |

BetaNYC's executive director, Noel Hidalgo, testified at the 2026-10-05 hearing; his testimony is transcribed and labeled the same way as everyone else's.

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
| `transcript/turns.csv`, `turns.json` | CSV, JSON | One row per speaker turn: `turn_id, start_sec, end_sec, start_hms, end_hms, speaker_name, speaker_role, confidence, deepgram_cluster, text_clean, text_unedited`, plus `mixed` (`true`/`false`) from 2026-10-16 on: the turn holds more than one voice and is credited to the person named on it |
| `transcript/words.json` | JSON | `[{turn_id, word, start, end}]`, every recognized word with its timing |
| `transcript/captions.vtt` | WebVTT | Captions with the speaker in a `<v>` tag; cues of 7 seconds or less, at most two lines |
| `speakers.csv` | CSV | `speaker_name, speaker_role, category, turns, talk_seconds, first_heard_hms` |
| `legistar/` | PDF, DOCX, CSV | The Council's documents for the hearing, plus `manifest.csv` (source URL and last-modified time for each) |
| `media/` | Opus, README | Small audio file; links to the video and the full-quality MP3 |
| `city-qa.html` | HTML | "What the City said": every question Council Members asked the administration's panel, with the full exchange from the transcript, the follow-ups the City promised and its position on each bill. Built by `scripts/build_qa.py` from `scripts/meta/<slug>-city-qa.json` |
| `panels.json` | JSON | When present: the hearing's parts in order, `[{panel_id, title, start_hms, end_hms, turn_ids, members:[{name, role, org}]}]`; `turn_ids` are `turn_id`s in `turns.csv`, each in at most one panel |
| `panels.html` | HTML | When `panels.json` is present: "Who spoke, panel by panel", a timeline of every turn with the panels as bands, and talk time per panel. Built by `scripts/build_panels.py` |
| `lexicon.txt` | text | When present: the keyterms sent to Deepgram for this hearing, with sources (see [`lexicon/README.md`](lexicon/README.md)) |
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
| `ai-company` | `Witness — OpenAI`, `Anthropic`, `Meta`, `Google`, or `company panel` (the 2026-10-05 AI company panel), or `Witness — SpaceXAI` (2026-10-16) |
| `city-official` | `Witness — OTI`, `NYC Cyber Command / OTI`, `DCWP`, `NYC Emergency Management`, `NYC Equal Employment Practices Commission` |
| `witness` | Any other `Witness — …` role: advocates, researchers, unions, other companies, members of the public |

Smaller AI startups that testified in the public portion (for example Babble AI, Trina AI)
are `witness`, not `ai-company`. `ai-company` means a company the Council called to testify as
an AI company: the four on the invited panel on 2026-10-05, and SpaceXAI on 2026-10-16. A former
employee testifying on their own (for example Devin Kim, formerly of xAI) is `witness`.

## How it was made

1. **Video to audio.** The Council's video was converted to audio with ffmpeg
   (`scripts/fetch_media.py`, which also downloads the video and captions; the Council's
   documents come from `scripts/fetch_legistar.py`).
2. **Transcription.** Deepgram Nova-3 with speaker diarization. Diarization groups speech
   into voice clusters but does not know names.
3. **Turns.** Consecutive Deepgram segments with the same voice cluster and less than 5
   seconds between them are merged into one turn.
4. **Speaker names.** Assigned from self-introductions, the chair calling on people, on-screen
   labels (the Speaker's name banner on 2026-10-05; Zoom name labels on 2026-10-16, read from
   video frames), the Council's captions, and voice clusters, then cross-checked
   against the Legistar roster, titles and bill sponsors and NYS Open Legislation member and
   sponsor records. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person. Each turn carries a confidence (`high`, `medium`, `low`).
5. **Clean verbatim.** An AI-assisted copy edit: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
   timestamp and speaker label match the unedited transcript exactly.
6. **Exports.** `scripts/build_hearing.py` (Python standard library only) writes the
   transcripts, CSV and JSON exports, captions, `hearing.json`, the hearing README and
   `index.html`; `build_panels.py`, `build_wordclouds.py` and `build_qa.py` write the panel,
   word-cloud and Q&A pages, and `lexicon.txt` is written by hand. See
   [`scripts/README.md`](scripts/README.md).
7. **Word clouds.** `scripts/build_wordclouds.py` scores the 1- to 3-word phrases in the clean
   transcript with a weighted log-odds test (Monroe, Colaresi and Quinn 2008, "Fightin' Words")
   to find what each speaker group, and some individual speakers, said far more than everyone
   else. Groups, people and word lists are in `scripts/meta/wordclouds.json`. Groups come from
   the AI-assigned speaker labels, so a mislabeled turn counts toward the wrong group.

## Known limits

- **This is a machine transcript, not an official record of the Council.** Words and speaker
  names can be wrong. Check the video at the timestamp before quoting anyone.
- `[?]` after a name in the transcripts (and `low` in `turns.csv`) marks a low-confidence
  speaker label. Some hearings have short turns labeled Unidentified; each hearing's README
  gives the count.
- Diarization occasionally puts two voices in one turn, typically a question and the first
  words of the answer. The whole turn, and its talk time and words, are credited to the person
  named on it, so talk time and the word clouds are approximate. Where a hearing records them
  (2026-10-16 on), `turns.csv` marks these turns `mixed`; check the video before quoting one.
  The 2026-10-05 labels do not mark them, so how many there are is not known.
- Talk time is a turn's end minus its start, so it includes short pauses (under 5 seconds)
  inside a turn, not only speech.
- "Words" in a hearing's README and `hearing.json` counts the unedited Deepgram transcript
  (`words.json`). The word-cloud pages count words in the clean verbatim text, which has fewer
  (fillers and false starts removed), so the two do not add up to the same total.
- Unless a hearing's README says otherwise, witness names are spelled as the transcription heard them and have not been checked against a witness list or written testimony. Some are likely misspelled; corrections are welcome as GitHub issues.
- Word timings in `words.json` and `captions.vtt` come from the unedited transcript. The
  clean edit has no word timings of its own.
- Each hearing's README lists its own gaps.

## Corrections

Found a mistake, a wrong name or affiliation, or a missing document? Every page has a link at the
bottom, "Open an issue on GitHub", that opens the
[correction form](https://github.com/BetaNYC/hearings-transcripts/issues/new?template=correction.yml)
with the hearing and page already filled in. Tell us what is wrong, what it should say, and how you
know: a time in the video, a document or a link. We check each report against the source and fix
it in a pull request that rebuilds the pages. The form lives in
`.github/ISSUE_TEMPLATE/correction.yml`; the footer link is made by `scripts/feedback.py`.

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

**Before you start: what a clone of this repository cannot do.**

- **Transcription is not in this repository.** BetaNYC sends the audio to Deepgram from a script
  in its private workspace. To transcribe a hearing yourself you need your own paid Deepgram API
  key (`DEEPGRAM_API_KEY`; Deepgram bills by audio length) and must make the same request
  yourself; [`scripts/README.md`](scripts/README.md#3-deepgram-transcription) lists the model,
  options and output format.
- **`scripts/fetch_legistar.py` needs a Legistar Web API token** in `LEGISTAR_TOKEN`. NYC's
  Legistar API requires one (https://webapi.legistar.com/Home/Examples); ask the NYC Council
  for one.
- **The raw working files are not published.** Each hearing's Deepgram output, speaker labels and
  transcripts before export stay on BetaNYC's machines. A clone can rebuild
  the web pages from the published data (`build_hearing.py --index-only`, `build_panels.py`,
  `build_wordclouds.py`, `build_qa.py`) but cannot rerun a published hearing from scratch. To
  check our work instead, compare the published `turns.csv` against the Council's video.

Follow the checklist in [`docs/PIPELINE.md`](docs/PIPELINE.md). In short: download the
Council's documents with `scripts/fetch_legistar.py` and the video, captions and audio with
`scripts/fetch_media.py`; transcribe with Deepgram and render the raw text with
`scripts/render_deepgram_raw.py`; name speakers and write `panels.json`; make the clean verbatim
edit and check it with `scripts/validate_clean.py`; write `scripts/meta/<slug>.json` (copy an
existing one) and run `python3 scripts/build_hearing.py …`; then `python3 scripts/build_panels.py`
and `python3 scripts/build_wordclouds.py` (a hearing's own groups go in
`scripts/meta/<slug>-wordclouds.json`), `python3 scripts/build_hearing.py --index-only`, and
`python3 -m unittest discover -s scripts`. MP3s and video never go into git: the full-quality
MP3 goes to a GitHub Release and the video to the Internet Archive (GitHub also refuses files over
100 MB).
