#!/usr/bin/env python3
"""Build "Who spoke, panel by panel" (panels.html) for every hearing that has a panels.json.

Python 3.11 to 3.14, standard library only. No network access.

    python3 scripts/build_panels.py [--slug <slug>]     # default: every hearing with panels.json
    python3 scripts/build_hearing.py --index-only        # adds the page link to index.html and the README

Reads, from hearings/<slug>/:
  panels.json             [{panel_id, title, start_hms, end_hms, turn_ids, members:[{name, role, org}]}]
                          (copied in by build_hearing.py --panels, which validates it)
  transcript/turns.csv    turn times, speakers and clean text
  speakers.csv            each speaker's category
  hearing.json            title, date, duration, video links, mixed_turns

Writes hearings/<slug>/panels.html: one self-contained page (no external files except the
repository's own logo), with
  (a) a timeline of the whole hearing: the panels as bands across the top, one row per speaker
      grouped by category, each turn a bar at its real time and length. Hover or focus shows
      the speaker, time and first words; click, Enter or Space shows the turn's clean text;
      arrow keys move between turns in time order. The SVG is drawn here, so it reads without
      JavaScript; the script only adds the tooltip and the turn reader.
  (b) for each panel, who spoke and for how long (seconds from turn times), with the split
      between Council Members, Council staff and witnesses;
  (c) a note on method, and every turn as a table.

Colors: one hue per speaker category, validated with the dataviz palette checker (lightness,
chroma, colorblind separation and normal-vision separation between adjacent groups, light
mode). Council staff and unidentified speakers are neutral gray. Every color is paired with a
written label, and the tables carry every value, so nothing depends on color alone.

Re-running rewrites the page and produces identical bytes.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feedback import ABOUT_URL, feedback_html, repo_blob  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCRIPT = "build_panels"

# Category order on the timeline, label and color. The five hues pass the dataviz validator in
# this adjacent order on a white surface (all checks pass; #1baf7a and #eda100 are under 3:1
# against white, so every bar has a written row label and every value is in a table).
CATEGORY_STYLE = [
    ("council", "Council Members and the Speaker", "#2359a8"),
    ("ai-company", "AI company", "#eb6834"),
    ("witness", "Other witnesses", "#1baf7a"),
    ("city-official", "City officials", "#eda100"),
    ("state-or-other-elected", "State or other elected", "#6250d6"),
    ("council-staff", "Council staff", "#949494"),
    ("unidentified", "Unidentified", "#949494"),
]
CAT_LABEL = {k: lab for k, lab, _ in CATEGORY_STYLE}
CAT_COLOR = {k: col for k, _, col in CATEGORY_STYLE}
WITNESS_CATS = {"ai-company", "witness", "city-official", "state-or-other-elected"}
SIDES = [("Council Members", {"council"}), ("Council staff", {"council-staff"}),
         ("Witnesses", WITNESS_CATS), ("Unidentified", {"unidentified"})]

DISCLOSURE = ("Names were assigned by AI agents working from these sources, at BetaNYC's direction. "
              "Elected officials were checked against Legistar and NYS Open Legislation. "
              "Other names were not individually verified by a person.")

# Timeline geometry (SVG user units).
W, LABEL_W, RIGHT_PAD = 1100, 250, 16
BAND_H, BAND_GAP = 40, 8
GROUP_H, ROW_H, BAR_H = 28, 22, 14
AXIS_H = 34


def log(event: str, **kw) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"{ts} {SCRIPT} {event} " + " ".join(f"{k}={v}" for k, v in kw.items()), file=sys.stderr)


def die(msg: str) -> None:
    print(f"{SCRIPT}: ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def json_for_script(obj) -> str:
    """JSON safe inside <script>: every "<" becomes \\u003c, so transcript text can never close
    the script ("</script") or open an HTML comment ("<!--") that changes how it is parsed."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def hms_to_sec(s: str) -> int:
    h, m, sec = (int(x) for x in s.split(":"))
    return h * 3600 + m * 60 + sec


def hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def clock(sec: float) -> str:
    """Talk time as m:ss, or h:mm:ss from an hour."""
    s = int(round(sec))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def first_words(text: str, n: int = 14) -> str:
    words = text.split()
    return " ".join(words[:n]) + (" …" if len(words) > n else "")


def tick_step(duration: float) -> int:
    for step in (300, 600, 900, 1800, 3600):
        if duration / step <= 12:
            return step
    return 7200


# ---- data ------------------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        die(f"required input missing: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load(hdir: Path) -> tuple[dict, list[dict], list[dict]]:
    hearing = json.loads((hdir / "hearing.json").read_text(encoding="utf-8"))
    panels = json.loads((hdir / "panels.json").read_text(encoding="utf-8"))
    cats = {(s["speaker_name"], s["speaker_role"]): s["category"] for s in read_csv(hdir / "speakers.csv")}
    turns = []
    for r in read_csv(hdir / "transcript" / "turns.csv"):
        key = (r["speaker_name"], r["speaker_role"])
        if key not in cats:
            die(f"turn {r['turn_id']}: speaker {key} not in speakers.csv")
        if cats[key] not in CAT_COLOR:
            die(f"turn {r['turn_id']}: category {cats[key]!r} has no color in build_panels.py")
        turns.append({"i": int(r["turn_id"]), "start": float(r["start_sec"]), "end": float(r["end_sec"]),
                      "name": r["speaker_name"], "role": r["speaker_role"], "cat": cats[key],
                      "text": r["text_clean"]})
    ids = {t["i"] for t in turns}
    for p in panels:
        bad = [i for i in p["turn_ids"] if i not in ids]
        if bad:
            die(f"panel {p['panel_id']}: unknown turn ids {bad[:5]}")
    return hearing, panels, turns


def panel_of(panels: list[dict]) -> dict[int, int]:
    """turn id -> panel index (0-based)."""
    return {i: k for k, p in enumerate(panels) for i in p["turn_ids"]}


def speaker_rows(turns: list[dict]) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(category, [(name, role), ...])] in timeline order: categories in CATEGORY_STYLE order,
    speakers within a category by when they were first heard."""
    first: dict[tuple[str, str], float] = {}
    cat: dict[tuple[str, str], str] = {}
    for t in turns:
        k = (t["name"], t["role"])
        first[k] = min(first.get(k, t["start"]), t["start"])
        cat[k] = t["cat"]
    out = []
    for c, _, _ in CATEGORY_STYLE:
        people = sorted((k for k in first if cat[k] == c), key=lambda k: first[k])
        if people:
            out.append((c, people))
    return out


def panel_stats(panel: dict, turns_by_id: dict[int, dict]) -> dict:
    """Talk seconds per speaker and per side for one panel, from turn start and end times."""
    people: dict[tuple[str, str], dict] = {}
    sides = {name: 0.0 for name, _ in SIDES}
    for i in panel["turn_ids"]:
        t = turns_by_id[i]
        secs = t["end"] - t["start"]
        p = people.setdefault((t["name"], t["role"]), {"name": t["name"], "role": t["role"], "cat": t["cat"],
                                                        "turns": 0, "seconds": 0.0})
        p["turns"] += 1
        p["seconds"] += secs
        for side, cats in SIDES:
            if t["cat"] in cats:
                sides[side] += secs
    total = sum(sides.values())
    ranked = sorted(people.values(), key=lambda p: (-p["seconds"], p["name"]))
    heard = {p["name"] for p in ranked}
    unheard = [m for m in panel["members"] if m["name"] not in heard]
    return {"people": ranked, "sides": sides, "total": total, "unheard": unheard}


# ---- rendering -------------------------------------------------------------------------------
def band_label(title: str, width: float, number: int) -> str:
    """The band's own label, the longest that fits: the title up to its first ' (', then the
    title up to its first ':', then the part number (which matches the numbered list below)."""
    for cand in (title.split(" (")[0], title.split(":")[0]):
        if len(cand) * 7.2 + 12 <= width:
            return cand
    return str(number) if width >= 16 else ""


def timeline_svg(hearing: dict, panels: list[dict], turns: list[dict]) -> tuple[str, int]:
    duration = float(hearing["stats"].get("duration_sec") or max(t["end"] for t in turns))
    x0, x1 = LABEL_W, W - RIGHT_PAD

    def sx(sec: float) -> float:
        return x0 + max(0.0, min(sec, duration)) / duration * (x1 - x0)

    rows = speaker_rows(turns)
    y = BAND_H + BAND_GAP
    row_y: dict[tuple[str, str], float] = {}
    labels = []
    for c, people in rows:
        labels.append(f'<text class="grp" x="0" y="{y + 19}">{esc(CAT_LABEL[c])}</text>')
        y += GROUP_H
        for k in people:
            row_y[k] = y
            labels.append(f'<text class="who" x="12" y="{y + 15}">{esc(k[0])}</text>')
            y += ROW_H
    plot_bottom = y + 4
    height = int(plot_bottom + AXIS_H)
    parts = [f'<svg id="timeline" class="timeline" viewBox="0 0 {W} {height}" role="group" '
             f'aria-labelledby="tl-t tl-d" xmlns="http://www.w3.org/2000/svg">',
             '<title id="tl-t">Timeline of every speaker turn</title>',
             f'<desc id="tl-d">{len(turns)} turns over {esc(hms(duration))}, one row per speaker, grouped by '
             f'category, with the {len(panels)} parts of the hearing as bands across the top. '
             f'Every turn is also listed in the table below.</desc>']
    # Panel bands and guides.
    for k, p in enumerate(panels):
        a, b = sx(hms_to_sec(p["start_hms"])), sx(hms_to_sec(p["end_hms"]))
        fill = "#EEF4FF" if k % 2 == 0 else "#F1F1F1"
        parts.append(f'<g class="band"><title>{esc(p["title"])}, {esc(p["start_hms"])} to {esc(p["end_hms"])}</title>'
                     f'<rect x="{a:.1f}" y="0" width="{max(b - a, 1):.1f}" height="{BAND_H}" fill="{fill}"/>'
                     f'<text x="{a + 6:.1f}" y="{BAND_H / 2 + 5:.0f}">{esc(band_label(p["title"], b - a, k + 1))}</text></g>')
        parts.append(f'<line class="guide" x1="{a:.1f}" x2="{a:.1f}" y1="{BAND_H}" y2="{plot_bottom}"/>')
    # Axis.
    step = tick_step(duration)
    for v in range(0, int(duration) + 1, step):
        gx = sx(v)
        parts.append(f'<line class="grid" x1="{gx:.1f}" x2="{gx:.1f}" y1="{BAND_H + BAND_GAP}" y2="{plot_bottom}"/>')
        parts.append(f'<text class="tick" x="{gx:.1f}" y="{plot_bottom + 20}" text-anchor="middle">'
                     f'{v // 3600}:{v % 3600 // 60:02d}</text>')
    parts.append(f'<line class="axis" x1="{x0}" x2="{x1}" y1="{plot_bottom}" y2="{plot_bottom}"/>')
    parts.extend(labels)
    # Turns, in time order (the tab order).
    for t in sorted(turns, key=lambda t: (t["start"], t["i"])):
        ty = row_y[(t["name"], t["role"])]
        a, b = sx(t["start"]), sx(t["end"])
        w = max(b - a, 2.0)
        hit_w = max(w, 8.0)
        hit_x = a - (hit_w - w) / 2
        label = (f"{t['name']}, {hms(t['start'])} to {hms(t['end'])}, {clock(t['end'] - t['start'])}: "
                 f"{first_words(t['text'], 10)}")
        parts.append(f'<g class="turn" tabindex="0" role="button" data-i="{t["i"]}" aria-label="{esc(label)}">'
                     f'<rect class="hit" x="{hit_x:.1f}" y="{ty:.1f}" width="{hit_w:.1f}" height="{ROW_H}"/>'
                     f'<rect class="mark" x="{a:.1f}" y="{ty + (ROW_H - BAR_H) / 2:.1f}" width="{w:.1f}" '
                     f'height="{BAR_H}" rx="2" fill="{CAT_COLOR[t["cat"]]}"/></g>')
    parts.append("</svg>")
    return "\n".join(parts), height


def legend(turns: list[dict]) -> str:
    present = {t["cat"] for t in turns}
    items = "".join(f'<li><span class="sw" style="background:{c}" aria-hidden="true"></span>{esc(lab)}</li>'
                    for k, lab, c in CATEGORY_STYLE if k in present)
    return f'<ul class="legend" aria-label="Colors: speaker category">{items}</ul>'


def share(secs: float, total: float) -> str:
    """Percent of a part's talk time; a nonzero share that rounds to 0 shows as "<1%"."""
    pct = secs / total * 100
    return "<1%" if 0 < pct < 0.5 else f"{pct:.0f}%"


def panel_section(k: int, p: dict, st: dict) -> str:
    total = st["total"] or 1.0
    top = max((x["seconds"] for x in st["people"]), default=1.0) or 1.0
    split = " · ".join(f"{side} {clock(secs)} ({share(secs, total)})"
                       for side, secs in st["sides"].items() if secs > 0)
    rows = []
    for x in st["people"]:
        pct = x["seconds"] / top * 78  # leave room after the longest bar for its value
        rows.append(f'<tr><th scope="row">{esc(x["name"])}</th><td>{esc(x["role"])}</td>'
                    f'<td class="num">{x["turns"]}</td>'
                    f'<td class="barcell"><span class="hbar" style="width:{pct:.1f}%;background:{CAT_COLOR[x["cat"]]}" '
                    f'aria-hidden="true"></span><span class="val">{clock(x["seconds"])}</span></td>'
                    f'<td class="num">{x["seconds"]:.0f}</td></tr>')
    unheard = ""
    if st["unheard"]:
        unheard = ('<p class="note">Listed for this part but not heard speaking: '
                   + esc("; ".join(f"{m['name']} ({m['org']})" for m in st["unheard"])) + ".</p>")
    pid = f"p-{esc(p['panel_id'])}"
    return f"""<section class="card panel" aria-labelledby="{pid}">
<h3 id="{pid}">{k + 1}. {esc(p['title'])}</h3>
<p class="note">{esc(p['start_hms'])} to {esc(p['end_hms'])} · {len(p['turn_ids'])} turns · {clock(st['total'])} of talk</p>
<p class="split"><strong>Who had the floor:</strong> {esc(split) if split else 'no turns'}</p>
<table class="talk"><caption class="vh">Talk time by speaker, {esc(p['title'])}</caption>
<thead><tr><th scope="col">Speaker</th><th scope="col">Role</th><th scope="col" class="num">Turns</th><th scope="col">Talk time</th><th scope="col" class="num">Seconds</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
{unheard}
</section>"""


def turns_table(turns: list[dict], panels: list[dict]) -> str:
    pof = panel_of(panels)
    rows = "".join(
        f'<tr><td class="num">{t["i"]}</td><td>{hms(t["start"])}</td><td>{hms(t["end"])}</td>'
        f'<td class="num">{t["end"] - t["start"]:.0f}</td><td>{esc(t["name"])}</td><td>{esc(t["role"])}</td>'
        f'<td>{(pof[t["i"]] + 1) if t["i"] in pof else ""}</td></tr>' for t in turns)
    return (f'<details id="all-turns"><summary>Every turn as a table ({len(turns)} rows)</summary>'
            f'<table><caption>Every speaker turn in time order. Part numbers match the bands and the sections below.</caption>'
            f'<thead><tr><th scope="col" class="num">Turn</th><th scope="col">Start</th><th scope="col">End</th>'
            f'<th scope="col" class="num">Seconds</th><th scope="col">Speaker</th><th scope="col">Role</th>'
            f'<th scope="col">Part</th></tr></thead><tbody>{rows}</tbody></table></details>')


STYLE = """
:root { --blue:#2359a8; --text:#414141; --muted:#595959; --border:#949494; --grid:#e6e6e6; --bg-blue:#EEF4FF; }
* { box-sizing:border-box; }
body { margin:0; font-family:Poppins, "Helvetica Neue", Arial, sans-serif; font-size:17px; line-height:30px; color:var(--text); background:#fff; }
.wrap { max-width:1230px; margin:0 auto; padding:0 max(1.25rem, 5vw); }
header.site { border-bottom:1px solid var(--border); padding:16px 0; }
header.site img { height:48px; width:auto; display:block; }
h1 { font-family:Poppins, "Helvetica Neue", Arial, sans-serif; font-weight:700; font-size:clamp(30px, 4.5vw, 44px); line-height:1.3; color:#000; margin:24px 0 8px; }
h2, h3 { font-family:Roboto, "Helvetica Neue", Arial, sans-serif; font-weight:700; color:#000; }
h2 { font-size:24px; line-height:34px; margin:36px 0 8px; }
h3 { font-size:20px; line-height:30px; margin:0 0 4px; }
a { color:var(--blue); text-decoration:underline; }
a:focus-visible, summary:focus-visible { outline:3px solid var(--blue); outline-offset:2px; }
.crumbs { font-size:15px; margin:16px 0 0; }
.sub { color:var(--muted); font-size:15px; line-height:24px; margin:0 0 8px; max-width:900px; }
.note { font-size:15px; line-height:24px; color:var(--muted); margin:0 0 12px; }
.card { border:1px solid var(--border); border-radius:0; padding:24px; margin:24px 0; background:#fff; }
.legend { list-style:none; padding:0; margin:8px 0; display:flex; flex-wrap:wrap; gap:4px 24px; font-size:15px; }
.legend .sw { display:inline-block; width:14px; height:14px; margin-right:7px; vertical-align:-1px; }
.scroll { overflow-x:auto; }
svg.timeline { width:100%; min-width:760px; height:auto; display:block; font-family:Roboto, "Helvetica Neue", Arial, sans-serif; }
svg.timeline text { font-size:13px; fill:#414141; }
svg.timeline text.grp { font-weight:700; fill:#000; font-size:14px; }
svg.timeline text.tick { fill:#595959; font-size:12px; }
svg.timeline .band text { font-size:13px; fill:#000; }
svg.timeline line.grid { stroke:var(--grid); stroke-width:1; }
svg.timeline line.guide { stroke:#c8c8c8; stroke-width:1; }
svg.timeline line.axis { stroke:var(--border); stroke-width:1; }
svg.timeline rect.hit { fill:transparent; }
svg.timeline g.turn { cursor:pointer; outline:none; }
svg.timeline g.turn:hover rect.mark, svg.timeline g.turn:focus rect.mark { stroke:#000; stroke-width:2; }
svg.timeline g.turn.sel rect.mark { stroke:#000; stroke-width:2; }
.reader { background:var(--bg-blue); padding:16px 24px; margin:16px 0; max-width:900px; min-height:60px; }
.reader h3 { margin:0; }
.reader p { margin:8px 0 0; }
.tip { position:fixed; pointer-events:none; background:#fff; color:var(--text); border:1px solid var(--border); padding:8px 10px; font-size:14px; line-height:20px; box-shadow:0 2px 8px rgba(0,0,0,.12); display:none; max-width:320px; z-index:2; }
.tip strong { color:#000; }
.panels { max-width:960px; }
.split { font-size:15px; line-height:24px; margin:0 0 8px; }
table { border-collapse:collapse; font-size:15px; line-height:22px; }
th, td { border:1px solid var(--border); padding:4px 8px; text-align:left; vertical-align:middle; }
table.talk { width:100%; }
table.talk th[scope=row] { font-weight:400; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
td.barcell { width:45%; white-space:nowrap; }
.hbar { display:inline-block; height:14px; min-width:2px; border-radius:0 4px 4px 0; vertical-align:-2px; margin-right:6px; }
.val { font-variant-numeric:tabular-nums; }
.vh { position:absolute; left:-9999px; }
details { margin:11px 0; }
summary { cursor:pointer; color:var(--blue); }
.how { max-width:750px; }
footer { border-top:1px solid var(--border); margin-top:54px; padding:24px 0; font-size:15px; }
"""

SCRIPT_JS = r"""
const tip=document.getElementById('tip'),reader=document.getElementById('reader');
const byId=new Map(TURNS.map(t=>[t.i,t]));
const marks=[...document.querySelectorAll('g.turn')];
function hms(s){s=Math.floor(s);const p=n=>String(n).padStart(2,'0');return p(Math.floor(s/3600))+':'+p(Math.floor(s%3600/60))+':'+p(s%60)}
function dur(s){s=Math.round(s);return s>=60?Math.floor(s/60)+' min '+(s%60)+' s':s+' s'}
function words(x,n){const w=x.split(/\s+/);return w.slice(0,n).join(' ')+(w.length>n?' …':'')}
function el(tag,text,cls){const e=document.createElement(tag);if(cls)e.className=cls;e.textContent=text;return e}
function show(g,ev){const t=byId.get(+g.dataset.i);tip.replaceChildren(el('strong',t.n),document.createElement('br'),
  el('span',hms(t.s)+' to '+hms(t.e)+' · '+dur(t.e-t.s)),document.createElement('br'),el('span',words(t.t,14)));
 tip.style.display='block';let x,y;if(ev&&ev.clientX!==undefined){x=ev.clientX+14;y=ev.clientY+14}else{const r=g.getBoundingClientRect();x=r.left;y=r.bottom+8}
 const w=tip.offsetWidth,h=tip.offsetHeight;if(x+w>innerWidth-8)x=innerWidth-w-8;if(y+h>innerHeight-8)y=Math.max(8,y-h-36);
 tip.style.left=x+'px';tip.style.top=y+'px'}
function hide(){tip.style.display='none'}
function open(g){const t=byId.get(+g.dataset.i);marks.forEach(m=>m.classList.toggle('sel',m===g));
 reader.replaceChildren(el('h3',t.n+(t.r&&t.r!==t.n?' ('+t.r.replace(/^Witness — /,'')+')':'')),
  el('p',hms(t.s)+' to '+hms(t.e)+' · turn '+t.i+' · '+dur(t.e-t.s),'note'),el('p',t.t))}
marks.forEach((g,k)=>{g.addEventListener('pointermove',e=>show(g,e));g.addEventListener('pointerleave',hide);
 g.addEventListener('focus',()=>show(g));g.addEventListener('blur',hide);g.addEventListener('click',()=>open(g));
 g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(g)}
  else if(e.key==='ArrowRight'||e.key==='ArrowDown'){e.preventDefault();(marks[k+1]||g).focus()}
  else if(e.key==='ArrowLeft'||e.key==='ArrowUp'){e.preventDefault();(marks[k-1]||g).focus()}
  else if(e.key==='Escape'){hide()}})});
"""


def long_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def render(hearing: dict, panels: list[dict], turns: list[dict]) -> str:
    svg, _ = timeline_svg(hearing, panels, turns)
    by_id = {t["i"]: t for t in turns}
    sections = "\n".join(panel_section(k, p, panel_stats(p, by_id)) for k, p in enumerate(panels))
    name = f"{hearing['body']}, {long_date(hearing['date'])}"
    mixed = hearing.get("mixed_turns")
    mixed_txt = (f"{mixed} of the {len(turns)} turns hold two speakers" if mixed
                 else "Some turns hold two speakers")
    js_turns = [{"i": t["i"], "s": round(t["start"], 2), "e": round(t["end"], 2), "n": t["name"],
                 "r": t["role"], "t": t["text"]} for t in turns]
    keys = "".join(f"<li>{esc(p['title'])} <span class=\"note\">{esc(p['start_hms'])} to {esc(p['end_hms'])}</span></li>"
                   for p in panels)
    root, slug = "../../", hearing["slug"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Who spoke, panel by panel · {esc(name)} · BetaNYC</title>
<meta name="description" content="Every speaker turn at the {esc(name)} hearing on a timeline, and talk time for each panel.">
<style>{STYLE}</style>
</head>
<body>
<a href="#main" class="note" style="position:absolute;left:-999px" onfocus="this.style.left='8px'" onblur="this.style.left='-999px'">Skip to content</a>
<header class="site"><div class="wrap"><a href="https://beta.nyc/"><img src="{root}assets/betanyc-logo.svg" alt="BetaNYC home" width="142" height="48"></a></div></header>
<main id="main" class="wrap">
<p class="crumbs"><a href="{root}index.html#h-{esc(slug)}">{esc(name)}</a> › <a href="{repo_blob(f'hearings/{slug}/README.md')}">Hearing README</a></p>
<h1>Who spoke, panel by panel</h1>
<p class="sub">{esc(hearing['title'])}. {esc(name)}, {esc(hearing['video']['duration_hms'])} of video, {len(turns)} speaker turns in {len(panels)} parts.</p>

<h2 id="tl-h">The whole hearing</h2>
<p class="note">Each bar is one turn, placed at its time in the recording and as long as it lasted. Bands across the top are the parts of the hearing. Hover or tab to a bar for the speaker and first words; click it, or press Enter, to read the turn below. Arrow keys move between turns in time order. <a href="#all-turns">Skip to the table of every turn</a>.</p>
{legend(turns)}
<div class="scroll">
{svg}
</div>
<ol class="note" aria-label="Parts of the hearing">{keys}</ol>
<section id="reader" class="reader" aria-live="polite" aria-label="Selected turn"><p class="note">Select a turn to read it here.</p></section>

<h2 id="pn-h">Each part: who spoke, and for how long</h2>
<p class="note">Talk time is the sum of each speaker's turns in that part, from the turn start and end times, in minutes and seconds. Bars compare speakers within one part. Council Members includes the Speaker and the chair; witnesses includes everyone who testified.</p>
<div class="panels">
{sections}
</div>

{turns_table(turns, panels)}

<h2 id="how-h">How this was made</h2>
<div class="how">
<p>Speaker turns come from the Deepgram transcript, merged by voice and gap as described in the repository README; the parts of the hearing and who sat on each are in <a href="panels.json"><code>panels.json</code></a>. Times are seconds from the start of the Council's recording, not the clock time of the hearing.</p>
<p>Speaker names come from self-introductions, the chair calling on people, and voice clusters. {esc(DISCLOSURE)}</p>
<p>Talk time is approximate. {esc(mixed_txt)}: a question and the start of its answer, for example, where the diarization did not split them. Those turns count toward the person named on the turn.</p>
<p>Built by <code>scripts/build_panels.py</code> from <code>panels.json</code>, <code>transcript/turns.csv</code> and <code>speakers.csv</code>. This is a machine transcript, not an official record; check the video before quoting anyone.</p>
</div>
</main>
<footer><div class="wrap">{feedback_html(f"hearings/{slug}/panels.html", hearing)}BetaNYC · <a href="https://beta.nyc/">beta.nyc</a> · <a href="{root}index.html">All hearing transcripts</a> · <a href="{ABOUT_URL}">About this repository</a></div></footer>
<div class="tip" id="tip" aria-hidden="true"></div>
<script>
const TURNS={json_for_script(js_turns)};
{SCRIPT_JS}</script>
</body>
</html>
"""


def build(slug: str) -> Path:
    hdir = REPO / "hearings" / slug
    hearing, panels, turns = load(hdir)
    out = hdir / "panels.html"
    text = render(hearing, panels, turns)
    if not out.is_file() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    log("panels_written", slug=slug, panels=len(panels), turns=len(turns), bytes=out.stat().st_size)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slug", action="append", help="hearing slug (repeatable); default: every hearing with panels.json")
    a = ap.parse_args(argv)
    slugs = a.slug or sorted(p.parent.name for p in (REPO / "hearings").glob("*/panels.json"))
    if not slugs:
        die("no hearings with panels.json")
    for s in slugs:
        build(s)


if __name__ == "__main__":
    main()
