# Word cloud fixtures

Output of the approved prototype scorer (`distinct.py`, 2026-10-06), run on this repository's
`turns.csv`, renamed to the group slugs in `scripts/meta/wordclouds.json`:

| Fixture | Prototype group |
|---|---|
| `whistleblower-panel.json` | `whistleblower` |
| `ai-companies.json` | `ai-company` |
| `city-officials.json` | `city-official` |
| `council-members.json` | `council` (without Julie Menin and Carmen De La Rosa) |
| `public-witnesses.json` | `witness` (without the whistleblower panel) |
| `other-electeds.json` | `state-or-other-elected` |

In each, `panel` is the group's count and `rest` is everyone else's. `scripts/test_wordclouds.py`
requires the top 45 phrases, counts and z-scores to match exactly.
