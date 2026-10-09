#!/usr/bin/env python3
"""Build a "what the City said" Q&A page for one hearing panel.

Pure standard library. No network access. Reuses the word cloud pages' style.

  python3 scripts/build_qa.py --config scripts/meta/2026-10-05-committee-of-the-whole-ai-city-qa.json

Reads   scripts/meta/<slug>-city-qa.json (sections, question headlines, follow-ups)
        hearings/<slug>/transcript/turns.json, hearings/<slug>/hearing.json
Writes  hearings/<slug>/<page>

The exchanges are the transcript's own turns, word for word. Only the question headlines,
titles, bill-position table and follow-up list are written by hand, in the config file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_wordclouds import FONTS, STYLE, esc, footer, long_date, site_header  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

QA_STYLE = """
.toc ol { padding-left:20px; margin:8px 0; }
.toc li { margin:2px 0; }
.qs { padding-left:20px; margin:8px 0 16px; }
.turn { margin:0 0 16px; padding:8px 0 8px 16px; border-left:4px solid var(--grid); max-width:900px; }
.turn.city { border-left-color:var(--blue); background:var(--bg-blue); padding-right:16px; }
.turn .who { font-weight:700; color:#000; }
.turn .who .t { font-weight:400; color:var(--muted); font-size:15px; }
.turn p { margin:4px 0 0; }
.turn .flag { font-size:14px; line-height:20px; color:var(--muted); font-style:italic; }
.turn:target { outline:3px solid var(--blue); outline-offset:2px; }
.key { display:inline-block; width:14px; height:14px; background:var(--bg-blue); border-left:4px solid var(--blue); vertical-align:middle; }
"""


def hms_to_sec(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def turn_at(turns: list[dict], hms: str) -> dict:
    """The turn that is speaking at this video time."""
    sec = hms_to_sec(hms)
    best = turns[0]
    for t in turns:
        if t["start_sec"] <= sec + 1:
            best = t
    return best


def section_turns(by_id: dict, sec: dict) -> list[dict]:
    ids = list(range(sec["turns"][0], sec["turns"][1] + 1))
    if "extra_turns" in sec:
        ids += range(sec["extra_turns"][0], sec["extra_turns"][1] + 1)
    return [by_id[i] for i in sorted(ids)]


def render_turn(t: dict, officials: set[str], notes: dict) -> str:
    name = t["speaker_name"]
    city = name in officials or str(t["turn_id"]) in notes and "administration" in notes[str(t["turn_id"])]
    label = "Unidentified administration speaker" if name.startswith("Unidentified") and city else name
    flag = f'<p class="flag">{esc(notes[str(t["turn_id"])])}</p>' if str(t["turn_id"]) in notes else ""
    return (f'<div class="turn{" city" if city else ""}" id="t{t["turn_id"]}">'
            f'<span class="who">{esc(label)} <span class="t">{esc(t["start_hms"])}</span></span>'
            f'<p>{esc(t["text_clean"])}</p>{flag}</div>')


def build(cfg_path: Path) -> Path:
    cfg = json.loads(cfg_path.read_text())
    hdir = REPO / "hearings" / cfg["slug"]
    hearing = json.loads((hdir / "hearing.json").read_text())
    turns = json.loads((hdir / "transcript" / "turns.json").read_text())
    by_id = {t["turn_id"]: t for t in turns}
    officials = {o["name"] for o in cfg["officials"]}
    notes = cfg.get("speaker_notes", {})
    hearing_name = f"{hearing['body']}, {long_date(hearing['date'])}"
    root = "../../"

    toc = "".join(f'<li><a href="#{s["id"]}">{esc(s["who"])}</a> ({len(s["questions"])})</li>'
                  for s in cfg["sections"])
    who_rows = "".join(f"<tr><td>{esc(o['name'])}</td><td>{esc(o['title'])}</td></tr>" for o in cfg["officials"])
    pos_rows = "".join(f"<tr><td>{esc(b)}</td><td>{esc(w)}</td><td>{esc(p)}</td></tr>" for b, w, p in cfg["positions"])
    fu_rows = "".join(
        f'<tr><td>{esc(w)}</td><td>{esc(to)}</td><td>{esc(what)}</td>'
        f'<td><a href="#t{turn_at(turns, hms)["turn_id"]}">{esc(hms)}</a></td></tr>'
        for w, to, what, hms in cfg["followups"])

    opening = "".join(render_turn(by_id[i], officials, notes) for i in cfg["opening"]["turns"])
    words = sum(len(by_id[i]["text_clean"].split()) for i in cfg["opening"]["turns"])

    sections = []
    for s in cfg["sections"]:
        ts = section_turns(by_id, s)
        qs = "".join(f'<li><a href="#t{turn_at(ts, hms)["turn_id"]}">{esc(q)}</a> <span class="note">{esc(hms)}</span></li>'
                     for hms, q in s["questions"])
        body = "".join(render_turn(t, officials, notes) for t in ts)
        sections.append(f'<section class="card" id="{s["id"]}" aria-labelledby="{s["id"]}-h">'
                        f'<h2 id="{s["id"]}-h">{esc(s["who"])}</h2>'
                        f'<p class="note">Questions asked (click one to jump to it):</p><ol class="qs">{qs}</ol>'
                        f'<h3>The exchange, from the transcript</h3>{body}'
                        f'<p class="note"><a href="#top">Back to the list of Council Members</a></p></section>')

    p = cfg["panel"]
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(cfg['title'])} · {esc(hearing_name)} · BetaNYC</title>
<meta name="description" content="Every question Council Members asked the City's panel at the {esc(hearing_name)} hearing on AI, and the administration's answers, from BetaNYC's transcript.">
{FONTS}
<style>{STYLE}{QA_STYLE}</style>
</head>
<body>
{site_header(root)}
<main id="main" class="wrap">
<p class="crumbs" id="top"><a href="{root}index.html#h-{esc(hearing['slug'])}">{esc(hearing_name)}</a> › <a href="wordclouds/index.html">What each group talked about</a></p>
<h1>{esc(cfg['title'])}</h1>
<p class="sub">{esc(hearing['title'])}. {esc(p['summary'])} In the video it runs from {esc(p['start_hms'])} to {esc(p['end_hms'])}.</p>
<p class="brief">Each Council Member's questions are listed first, then the full exchange from the transcript. <span class="key"></span> Shaded turns are labeled as the administration.</p>

<section class="card toc" aria-labelledby="toc-h">
<h2 id="toc-h">Who asked questions</h2>
<ol>{toc}</ol>
<p class="note"><a href="#followups">What the City said it would follow up on</a> · <a href="#positions">The City's position on each bill</a> · <a href="#opening">Opening statement</a> · <a href="#how">How this page was made</a></p>
</section>

<section class="card" aria-labelledby="panel-h">
<h2 id="panel-h">Who spoke for the City</h2>
<table><thead><tr><th scope="col">Name</th><th scope="col">Title</th></tr></thead><tbody>{who_rows}</tbody></table>
<p class="note">{esc(cfg['titles_note'])}</p>
</section>

{''.join(sections)}

<section class="card" id="followups" aria-labelledby="fu-h">
<h2 id="fu-h">What the City said it would follow up on</h2>
<table><thead><tr><th scope="col">Who promised</th><th scope="col">To</th><th scope="col">What</th><th scope="col">Turn</th></tr></thead><tbody>{fu_rows}</tbody></table>
</section>

<section class="card" id="positions" aria-labelledby="pos-h">
<h2 id="pos-h">The City's position on each bill</h2>
<p class="note">Our short summary of the opening statement. Read the statement itself below.</p>
<table><thead><tr><th scope="col">Bill</th><th scope="col">What it does</th><th scope="col">The City's position</th></tr></thead><tbody>{pos_rows}</tbody></table>
</section>

<section class="card" id="opening" aria-labelledby="open-h">
<h2 id="open-h">Opening statement</h2>
<details><summary>Read Sarah Milstein's opening statement for OTI and DCWP ({words:,} words, {esc(cfg['opening']['start_hms'])})</summary>{opening}</details>
</section>

<section class="card how" id="how" aria-labelledby="how-h">
<h2 id="how-h">How this page was made</h2>
<p>The exchanges are copied from BetaNYC's machine transcript of the Council's video, in its clean edition: an AI-assisted edit that removes filler words, stutters and false starts and corrects words the transcription clearly misheard. They are not the Council's official transcript.</p>
<p>Speaker names come from the transcript's speaker labels. Sometimes one labeled turn holds words from more than one speaker, including a Council Member's question inside an official's answer. Those turns carry a note. Check the video before quoting anyone.</p>
<p>The question headlines, titles, bill-position summary and follow-up list were written by BetaNYC from the transcript.</p>
</section>
</main>
{footer(root)}
</body>
</html>
"""
    out = hdir / cfg["page"]
    out.write_text(page)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, type=Path)
    print(build(ap.parse_args().config))


if __name__ == "__main__":
    main()
