# NYC Council Committee on Technology: Oversight - Continuing Discussion about the Risks Posed by Artificial Intelligence

**2026-10-16, 10:00, Council Chambers, City Hall, New York, NY.** Legistar event
[22795](https://nyc.legistar.com/MeetingDetail.aspx?LEGID=22795&GID=61&G=2FD004F1-D85B-4588-A648-0A736C77D6E3). Video length 01:57:28.

- Internet Archive copy: [archive.org](https://archive.org/details/nyc-council-technology-ai-2026-10-16) (The Internet Archive copy is still being processed and may not play yet; until it does, watch the Council's video.)
- Council's own video: [councilnyc.viebit.com](https://councilnyc.viebit.com/vod/?s=true&v=NYCC-PV-CH-CHA_261016-101016.mp4)

This is a machine transcript with speaker names added by BetaNYC. **It is not an official
record.** Check the video before quoting anyone.

## Files

| File | What it is |
|---|---|
| `hearing.json` | Machine-readable metadata: body, date, Legistar ids, video links, bills heard, counts |
| `transcript/transcript.txt` | Unedited transcript, one turn per paragraph: `[HH:MM:SS] Name: text` |
| `transcript/transcript-clean.txt` | Clean verbatim: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. |
| `transcript/turns.csv`, `turns.json` | One row per speaker turn: `turn_id, start_sec, end_sec, start_hms, end_hms, speaker_name, speaker_role, confidence, deepgram_cluster, text_clean, text_unedited, mixed`. `mixed` is `true` when the speaker labels record more than one voice in the turn; the turn is credited to the person named on it |
| `transcript/words.json` | Every word with its start and end time in seconds and its `turn_id` (unedited words) |
| `transcript/captions.vtt` | WebVTT captions, speaker in a `<v>` tag, cues of 7 seconds or less |
| `speakers.csv` | One row per speaker: `speaker_name, speaker_role, category, turns, talk_seconds, first_heard_hms` |
| `legistar/` | 2 documents from Legistar plus `manifest.csv` with each document's Legistar URL and last-modified time |
| `media/` | 16 kbps Opus audio, and pointers to the video and the full-quality MP3 |
| `panels.json` | The hearing's parts in order: `[{panel_id, title, start_hms, end_hms, turn_ids, members:[{name, role, org}]}]`. `turn_ids` are `turn_id`s in `turns.csv`; each turn is in at most one panel |
| `panels.html` | Who spoke, panel by panel: a timeline of every turn and talk time per panel (built by `scripts/build_panels.py`) |
| `lexicon.txt` | The keyterms sent to Deepgram for this hearing, with their sources |

Times are seconds from the start of the Council's recording (00:00:00 is the first frame,
not 10:00 AM).

## Bills and topics heard

Oversight topic: T2026-2684, Oversight - Continuing Discussion about the Risks Posed by Artificial Intelligence.

No bills were on the agenda; this was an oversight hearing only.

## Context

The committee report states that SpaceXAI was issued a subpoena to provide testimony before the City Council but did not appear during the Committee of the Whole's hearing on October 5, 2026; that SpaceXAI afterwards reached out to the Council and agreed to provide testimony at this October 16 hearing; and that the Committee expected testimony from SpaceXAI and other interested parties. (Source: Committee Report, T2026-2684, Committee on Technology, October 16, 2026, Introduction (Legistar attachment, last modified 2026-10-15), legistar/t2026-2684-committee-report.docx.)

Council Members heard on the recording: Julie Menin (Speaker); Carmen De La Rosa (Council Member); Virginia Maloney (Council Member); Jennifer Gutiérrez (Council Member); Mercedes Narcisse (Council Member). From the speaker labels (who is heard on the recording), not the committee roster; members who attended without speaking are not listed. Carmen De La Rosa chairs the Committee on Technology (Legistar).

## Counts

- Turns: 248; speakers (name and role pairs): 17; words (unedited Deepgram transcript): 17366
- Speaker-name confidence by turn: high 234, medium 13, low 1
- Turns with no identified speaker (category `unidentified`): 0

Speaker categories (derived from the role, see the repository README for the rule):

| Category | Meaning | Speakers |
|---|---|---|
| `council` | Council Member or Speaker | 5 |
| `council-staff` | Council staff | 2 |
| `city-official` | City official | 0 |
| `state-or-other-elected` | State or other elected | 0 |
| `ai-company` | AI company | 1 |
| `witness` | Other witness | 9 |
| `unidentified` | Unidentified | 0 |

<!-- panels:start -->
## Who spoke, panel by panel

[`panels.html`](panels.html) shows every speaker turn on a timeline of the hearing, with the
panels as bands, and each panel's talk time by speaker, Council and witnesses side by side.
Built by `scripts/build_panels.py` from `panels.json` and `transcript/turns.csv`.
<!-- panels:end -->

<!-- wordclouds:start -->
## What each group talked about

[`wordclouds/index.html`](wordclouds/index.html) shows, for each speaker group and for some
individual speakers, the phrases they used far more than everyone else at the hearing, as a
word cloud, a bar chart and a table. Each `wordclouds/<group>.csv` (and
`wordclouds/people/<person>.csv`) lists every phrase that passed: `phrase, group_count,
others_count, z`. Built by `scripts/build_wordclouds.py`; groups and word lists are in
`scripts/meta/2026-10-16-technology-ai-wordclouds.json` (which builds on `scripts/meta/wordclouds.json`).
<!-- wordclouds:end -->

## Known gaps

- Speaker names were assigned after transcription. A low-confidence name shows `[?]` in the
  transcripts and `low` in `turns.csv`. Some turns contain two voices (for example a question
  and the start of an answer) because the diarization did not split them.
- No turn is labeled Unidentified.
- Speaker names come from self-introductions, the chair calling on people, Zoom name labels read from video frames, the Council's own captions, and voice clusters. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person.
- Witness names follow the Zoom name label where one was shown on screen, and otherwise the transcription. The SpaceXAI witness is "Gabriela Castillo Madrid": that spelling matches her Zoom name label (checked in a video frame at 00:09:11) and press coverage (PIX11); the Council's captions have "Gabriella Madrid" at her self-introduction and "Christina Madrid" when counsel called her. Qiaojing Ella Zheng's firm, Sanford Heisler Sharp McKnight, was checked against public professional listings (Chambers, Daily Journal). Other names have not been checked against a witness list or written testimony; corrections are welcome as GitHub issues.
- The clean verbatim copy edit was AI-assisted: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
  timestamp and speaker label match the unedited transcript, which is kept alongside in every
  export.
- Talk time is approximate: 56 turns contain two voices. It runs from each turn's start to its end, so it
  includes short pauses (under 5 seconds) inside a turn. They are marked `mixed` in `turns.csv`; check the video before quoting one of them.
- Kalima gave only one name; no surname was found, so her label reads "Kalima [surname unknown]". Her group's own name is Demilitarize Brooklyn Navy Yard; in her testimony she says "Demilitarized", and the transcript keeps her words.
- Bryce Rogers, Megan Lagerquist, Ajeet Singh and Chowdhury Hasan Mahmud are spelled as they appeared at the hearing (Zoom labels, self-introductions); none was confirmed in public sources.
- "Sophie Cote" follows her Oct 16 Zoom label and is not confirmed elsewhere. She is very likely the speaker transcribed as "Sophie Cody" at the 2026-10-05 hearing.
- Steve Kramer's affiliation, "Get Out the Vote", is as stated at the hearing ("I own the firm Get Out the Vote", 01:46:32), not a verified firm name.
- Devin Kim is labeled "former xAI employee". Titles and accounts of how he left xAI appear only as he or Council Members said them in the transcript; BetaNYC has not verified them.
- The word lists for this hearing's word clouds were not reviewed by hand. They reuse the stopwords made for the 2026-10-05 hearing, so some filler (for example "obviously", "asked") remains.
- The Internet Archive copy is still being processed and may not play yet; until it does, watch the Council's video.
