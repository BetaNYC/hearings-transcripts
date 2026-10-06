# NYC Council Committee of the Whole: Oversight - Examining the Risks Posed by Artificial Intelligence

**2026-10-05, 11:00, City Hall, New York, NY.** Legistar event
[22752](https://nyc.legistar.com/MeetingDetail.aspx?LEGID=22752&GID=61&G=2FD004F1-D85B-4588-A648-0A736C77D6E3). Video length 10:08:12.

- Watch: [Internet Archive](https://archive.org/details/nyc-council-committee-of-the-whole-ai-2026-10-05) (The Internet Archive upload is still in progress; the item may not be playable yet.)
- Council's own video: [councilnyc.viebit.com](https://councilnyc.viebit.com/vod/?s=true&v=NYCC-PV-CH-CHA_261005-110828.mp4)

This is a machine transcript with speaker names added by BetaNYC. **It is not an official
record.** Check the video before quoting anyone.

BetaNYC's executive director, Noel Hidalgo, testified at this hearing; his testimony is transcribed and labeled the same way as everyone else's.

## Files

| File | What it is |
|---|---|
| `hearing.json` | Machine-readable metadata: body, date, Legistar ids, video links, bills heard, counts |
| `transcript/transcript.txt` | Unedited transcript, one turn per paragraph: `[HH:MM:SS] Name: text` |
| `transcript/transcript-clean.txt` | Clean verbatim: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. |
| `transcript/turns.csv`, `turns.json` | One row per speaker turn: `turn_id, start_sec, end_sec, start_hms, end_hms, speaker_name, speaker_role, confidence, deepgram_cluster, text_clean, text_unedited` |
| `transcript/words.json` | Every word with its start and end time in seconds and its `turn_id` (unedited words) |
| `transcript/captions.vtt` | WebVTT captions, speaker in a `<v>` tag, cues of 7 seconds or less |
| `speakers.csv` | One row per speaker: `speaker_name, speaker_role, category, turns, talk_seconds, first_heard_hms` |
| `legistar/` | 45 documents from Legistar plus `manifest.csv` with each document's Legistar URL and last-modified time |
| `media/` | 16 kbps Opus audio, and pointers to the video and the full-quality MP3 |

Times are seconds from the start of the Council's recording (00:00:00 is the first frame,
not 11:00 AM).

## Bills and topics heard

Oversight topic: T2026-2573, Oversight - Examining the Risks Posed by Artificial Intelligence.

| File | Subject | Lead sponsor |
|---|---|---|
| Int 0161-2026 | Algorithmic tools and their impact on city employees | Carmen De La Rosa |
| Int 0504-2026 | Unauthorized depiction of public officials by artificial intelligence | Nantasha Williams |
| T2026-2599 | Chatbot data privacy, security, and transparency | Frank Morano |
| T2026-2600 | Private cause of action for harms from third-party misuse of AI models | Virginia Maloney |
| T2026-2601 | Reporting and public disclosure of AI safety incidents concerning city contracts | Kamillah Hanks |
| T2026-2602 | Third-party validation and shut-down capability of AI models | Julie Menin |
| T2026-2603 | Disclosures and prohibiting deceptive representations in the promotion of AI models | Carl Wilson |
| T2026-2604 | Contractor whistleblower postings and protections related to AI | Kevin Riley |
| T2026-2605 | Civilian enforcement of AI violations | Julie Menin |
| T2026-2606 | AI model emergency response plan | Chi Ossé |

## Counts

- Turns: 830; speakers (name and role pairs): 106; words: 89181
- Speaker-name confidence by turn: high 608, medium 186, low 36
- Turns with no identified speaker (category `unidentified`): 22

Speaker categories (derived from the role, see the repository README for the rule):

| Category | Meaning | Speakers |
|---|---|---|
| `council` | Council Member or Speaker | 29 |
| `council-staff` | Council staff | 2 |
| `city-official` | City official | 5 |
| `state-or-other-elected` | State or other elected | 7 |
| `ai-company` | AI company | 4 |
| `witness` | Other witness | 53 |
| `unidentified` | Unidentified | 6 |

## Known gaps

- Speaker names were assigned after transcription. A low-confidence name shows `[?]` in the
  transcripts and `low` in `turns.csv`. Some turns contain two voices (for example a question
  and the start of an answer) because the diarization did not split them.
- 22 turns are labeled Unidentified: short interjections, audience
  remarks, off-mic presiding remarks, and a few witnesses whose names were not audible.
- Speaker names come from self-introductions, the chair calling on people, the on-screen name
  banner (shown only for the Speaker), and voice clusters. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person.
- Witness names are spelled as the transcription heard them and have not been checked against a witness list or written testimony. Some are likely misspelled; corrections are welcome as GitHub issues.
- The clean verbatim copy edit was AI-assisted: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
  timestamp and speaker label match the unedited transcript, which is kept alongside in every
  export.
- Talk time is approximate: a few turns contain two voices.
- The Internet Archive upload is still in progress; the item may not be playable yet.
