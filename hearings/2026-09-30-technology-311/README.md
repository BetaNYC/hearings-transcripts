# NYC Council Committee on Technology: Oversight - New York City’s 311 System

**2026-09-30, 13:00, 250 Broadway, 8th Floor, Hearing Room 3, New York, NY.** Legistar event
[22733](https://nyc.legistar.com/MeetingDetail.aspx?LEGID=22733&GID=61&G=2FD004F1-D85B-4588-A648-0A736C77D6E3). Video length 01:34:30.

- Watch: the Internet Archive copy has not been uploaded yet.
- Council's own video: [councilnyc.viebit.com](https://councilnyc.viebit.com/vod/?s=true&v=NYCC-250-8-3_260930-131436.mp4)

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
| `legistar/` | 33 documents from Legistar plus `manifest.csv` with each document's Legistar URL and last-modified time |
| `media/` | 16 kbps Opus audio, and pointers to the video and the full-quality MP3 |
| `panels.json` | The hearing's parts in order: `[{panel_id, title, start_hms, end_hms, turn_ids, members:[{name, role, org}]}]`. `turn_ids` are `turn_id`s in `turns.csv`; each turn is in at most one panel |
| `panels.html` | Who spoke, panel by panel: a timeline of every turn and talk time per panel (built by `scripts/build_panels.py`) |
| `lexicon.txt` | The keyterms sent to Deepgram for this hearing, with their sources |

Times are seconds from the start of the Council's recording (00:00:00 is the first frame,
not 1:00 PM).

## Bills and topics heard

Oversight topic: T2026-2556, Oversight - New York City’s 311 System.

| File | Subject | Lead sponsor |
|---|---|---|
| Int 0173-2026 | Use of global positioning system coordinates for 311 complaints and service requests | Eric Dinowitz |
| Int 0669-2026 | Referring 311 non-emergency traffic condition complaints to the transportation bureau of the police department | Nantasha Williams |
| Int 0800-2026 | Requiring the 311 customer service center to redirect requests for service or complaints to the appropriate agency | Lynn Schulman |

## Context

The committee report states that the Committee on Technology would hold an oversight hearing on New York City's 311 system and hear three bills (Int. No. 173, Dinowitz; Int. No. 669, Williams; Int. No. 800, Schulman), and that those invited to testify included representatives from the Office of Technology and Innovation (OTI), the 311 Customer Service Center, and members of the public. It states that OTI manages 311's operations and technology. (Source: Committee Report, T2026-2556, Committee on Technology, September 30, 2026, Introduction and Background (Legistar attachment, last modified 2026-09-30), legistar/t2026-2556-committee-report.docx.)

Council Members heard on the recording: Carmen De La Rosa (Council Member); Eric Dinowitz (Council Member); Lynn Schulman (Council Member); Kevin Riley (Council Member); Jennifer Gutiérrez (Council Member). From the speaker labels (who is heard on the recording), not the committee roster. The Council's meeting minutes also list Shahana Hanif and Julie Won as present; they did not speak. Carmen De La Rosa chairs the Committee on Technology (Legistar). Deputy Speaker Nantasha Williams, Int 0669's sponsor, did not attend; the chair read her statement (00:09:32).

## Counts

- Turns: 151; speakers (name and role pairs): 10; words (unedited Deepgram transcript): 16379
- Speaker-name confidence by turn: high 148, medium 2, low 1
- Turns with no identified speaker (category `unidentified`): 0

Speaker categories (derived from the role, see the repository README for the rule):

| Category | Meaning | Speakers |
|---|---|---|
| `council` | Council Member or Speaker | 5 |
| `council-staff` | Council staff | 2 |
| `city-official` | City official | 1 |
| `state-or-other-elected` | State or other elected | 0 |
| `ai-company` | AI company | 0 |
| `witness` | Other witness | 2 |
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
`scripts/meta/2026-09-30-technology-311-wordclouds.json` (which builds on `scripts/meta/wordclouds.json`).

[`city-qa.html`](city-qa.html) lists every question Council Members asked the City's panel,
with the administration's answers from the transcript. Built by
`scripts/build_qa.py`; question headlines and follow-ups are in
`scripts/meta/2026-09-30-technology-311-city-qa.json`.
<!-- wordclouds:end -->

## Known gaps

- Speaker names were assigned after transcription. A low-confidence name shows `[?]` in the
  transcripts and `low` in `turns.csv`. Some turns contain two voices (for example a question
  and the start of an answer) because the diarization did not split them.
- No turn is labeled Unidentified.
- Speaker names come from self-introductions, the chair calling on people, a Zoom name label read from a video frame, the Council's own captions and official transcript, and voice clusters. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person.
- Joe Morrisroe's name and title (Deputy Commissioner, NYC 311) follow OTI's written testimony in Legistar. "Chowdhury Hasan Mahmud" follows his own written briefing sheet, posted with the hearing testimony in Legistar, and his Zoom name label (video frame at 01:28:30); the Council's official transcript has "Chaudhury Hassan Mahmood" and the captions "CHAUDHARY HASSAN MAHMOOD". The Council's official transcript (Legistar attachment, posted 2026-11-02) was used as a second source for names and disputed words; corrections are welcome as GitHub issues.
- The clean verbatim copy edit was AI-assisted: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
  timestamp and speaker label match the unedited transcript, which is kept alongside in every
  export.
- Talk time is approximate: 61 turns contain two voices. It runs from each turn's start to its end, so it
  includes short pauses (under 5 seconds) inside a turn. They are marked `mixed` in `turns.csv`; check the video before quoting one of them.
- The in-person public witness gave only her surname, Jennings ("Miss Jennings" in the chair's call and the official transcript), so her label reads "Jennings [first name unknown]".
- Council Member Schulman's opening statement (00:08:09) describes a bill on complaints about conditions in city jails. At 00:25:59 she says that statement was for a different 311 bill. Int 0800-2026, as titled in Legistar, is about redirecting 311 requests to the appropriate agency.
- The Committee Counsel who read the affirmation is not named on tape (the committee report lists Irene Byhovsky as Legislative Counsel), so the label stays "Committee Counsel".
- Turn 31 (00:25:22) is one word, "'26", labeled as the chair with low confidence: the official transcript has no matching line for her there.
- Turn 143 (01:26:51) is in Deepgram's voice cluster for Joe Morrisroe, who had already been dismissed; it is labeled as Jennings because the captions and the official transcript give her these words ("I'm just wondering").
- The Council's official transcript sometimes runs two speakers together (for example 00:38:32 to 00:39:45, where Council Member Gutiérrez's questions appear under the Deputy Commissioner). Turns follow Deepgram's voice clusters there.
- Public Advocate Jumaane Williams submitted written testimony (in the Legistar hearing testimony attachment); he did not speak at the hearing.
- The word lists for this hearing's word clouds were not reviewed by hand. They reuse the stopwords made for the 2026-10-05 hearing.
- The video has not been uploaded to the Internet Archive yet.
- The full-quality MP3 has not been published as a GitHub Release yet.
