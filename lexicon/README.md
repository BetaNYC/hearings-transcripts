# Lexicon: keyterms for transcription

Deepgram Nova-3 accepts a short list of **keyterms** with each request: words and names it
should expect, which it then spells and capitalizes the way the list does. This folder
explains how BetaNYC builds those lists for Council hearings.

Reference: Deepgram, Keyterm Prompting, https://developers.deepgram.com/docs/keyterm. As of
2026-10-19 it says:

- up to 100 keyterms and 500 tokens per request (over the token limit, the request fails);
- "focus on the most important 20-50 terms";
- write proper nouns with the capitalization you want in the output, ordinary terms in lower case;
- avoid common words that are rarely misheard, and overly broad terms.

## Two tiers

| Tier | Where | Status |
|---|---|---|
| 1. NYC and NYS reference list | `lexicon/` (this folder) | **Planned, not built.** |
| 2. Per-hearing list | `hearings/<slug>/lexicon.txt` | In use from the 2026-10-16 hearing on. |

**Tier 1** will be a large reference of correctly spelled names: Council Members and staff
from the Legistar roster, State legislators from NYS Open Legislation, and City agency names
from the City's agency registry (NYC Open Data `t3jq-9nkf`). It is a list to pick from, not a
list to send. There are no tier 1 files yet.

**Tier 2** is the list actually sent to Deepgram for one hearing: only the people,
organizations and terms in that hearing, taken from that hearing's Legistar roster, committee
report and the Council's captions. Keep it short. Twenty to forty terms is normal.

## Do not send a big list to Deepgram

A keyterm is not a spelling hint applied after the fact. Deepgram uses it while it listens and
will choose a listed term over what was said when the two sound alike. The more names on the
list that are not in the room, the more chances it has to put one of them into someone's mouth.

This happened on 2026-10-19. The first run for the 2026-10-16 hearing used BetaNYC's own
workspace word list, which holds staff names. The SpaceX witness introduced herself, and the
Council's captions read "Gabriella Madrid". Deepgram wrote "Gabrielle Langston", the name of a
BetaNYC staff member on that list, who was not at the hearing. So:

- never send tier 1, or any organization's general list, as keyterms;
- never include BetaNYC names unless a BetaNYC person speaks at that hearing;
- build each hearing's list from that hearing's own sources.

What a hearing list did, 2026-10-16 hearing, run 2 against run 1: "Langston" went from 1 to 0
and the witness came out as "Gabriella Castillo Madrid". "Grock" went from 8 to 0 and
"SpaceX SI" from 9 to 1. "Menon" became "Menin" all 9 times. One got worse: the keyterm
"Gutiérrez" came out as "Gutirez" (twice), where run 1 had "Gutierrez" and the captions have
"GUTIERREZ". "Julie Won" did not help: "council member Wong", as in run 1 ("Wang"). Keyterms
are a nudge, not a fix. Check every name against a source in speaker naming.

## Format

UTF-8 text, one term per line. `#` starts a comment, either a whole line or after a term.
Blank lines are ignored. Each term, or each block of terms, carries a source comment:

```
# source: Legistar Web API, OfficeRecords for body 5213 (Committee on Technology) active 2026-10-16
Carmen De La Rosa
Julie Won

# source: Council captions, self-introduction at 00:09:21
Gabriella Madrid
```

Allowed sources: the Legistar Web API (roster, matter titles, attachments), documents attached
to the hearing in Legistar, the Council's caption file, and NYS Open Legislation. If a name's
spelling differs between sources, say so in the comment. Never add a term from memory.

## Use

The list is passed to BetaNYC's workspace transcription script with the organization list
turned off:

```sh
python deepgram_transcribe.py "$D/hearing-audio-64k.mp3" --out "$D/deepgram-intermediate.json" \
  --raw-out "$D/deepgram-response.json" \
  --keyterms-file ~/Code/hearings-transcripts/hearings/<slug>/lexicon.txt --no-core
```

(An absolute path: the command runs from the workspace `scripts/` folder, not from this
repository.)

The script checks the 100-term and 500-token limits before sending anything. The token count is
an approximation (words separated by spaces), not Deepgram's own tokenizer, so stay well under the
limit; Deepgram still enforces the real one.
