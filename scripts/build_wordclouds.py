#!/usr/bin/env python3
"""Build "what each group talked about" word cloud pages for a hearing.

Pure standard library. Tested range: Python 3.11 to 3.14. No network access.

  python3 scripts/build_wordclouds.py                      # every hearing with a turns.csv
  python3 scripts/build_wordclouds.py --slug 2026-10-05-committee-of-the-whole-ai

Reads   hearings/<slug>/transcript/turns.csv, hearings/<slug>/speakers.csv,
        hearings/<slug>/hearing.json, scripts/meta/wordclouds.json
Writes  hearings/<slug>/wordclouds/<group>.html and <group>.csv     (one per speaker group)
        hearings/<slug>/wordclouds/people/<person>.html and .csv    (one per listed person)
        hearings/<slug>/wordclouds/index.html                       (gallery)

Method: weighted log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi and
Quinn 2008, "Fightin' Words"), comparing one group's 1- to 3-word phrases from text_clean
with every other speaker's. A phrase is kept when the group used it at least
min_group_count times (min_person_count for one person) and its z-score is above
z_threshold. A shorter phrase is dropped when a longer kept phrase contains it and has at
least subsume_ratio of its count. Every rule and word list lives in the config file so the
next hearing reuses it unchanged. Re-running rewrites every output in full.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import functools
import html
import json
import math
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "scripts" / "meta" / "wordclouds.json"
MAX_FILE_BYTES = 100 * 1024 * 1024
CSV_FIELDS = ["phrase", "group_count", "others_count", "z"]
SENTENCE_SPLIT = re.compile(r"[.?!;:,()\n]+")
TOKEN = re.compile(r"[a-z][a-z0-9']*")
POSSESSIVE = re.compile(r"'s\b")
HYPHEN = re.compile(r"(?<=[a-z0-9])-(?=[a-z0-9])")


def log(event: str, **kw) -> None:
    fields = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} build_wordclouds {event} {fields}".rstrip(), file=sys.stderr)


def die(msg: str) -> None:
    log("error", msg=repr(msg))
    sys.exit(1)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def plural(n: int, word: str, words: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else (words or word + 's')}"


# ---- data -----------------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("method", "people_method", "display", "groups", "people", "stopwords", "capitalization"):
        if key not in cfg:
            die(f"{path}: missing key {key!r}")
    slugs = [g["slug"] for g in cfg["groups"]]
    if len(set(slugs)) != len(slugs):
        die(f"{path}: duplicate group slug")
    for p in cfg["people"]:
        if p["group"] not in slugs:
            die(f"{path}: person {p['name']!r} names unknown group {p['group']!r}")
    return cfg


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        die(f"required input missing: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def category_map(speakers: list[dict]) -> dict[tuple[str, str], str]:
    return {(s["speaker_name"], s["speaker_role"]): s["category"] for s in speakers}


def group_matcher(rule: dict, cats: dict[tuple[str, str], str]):
    """Return turn -> bool for a group's "match" rule.

    Keys (all optional, all must hold): category, role_contains, exclude_names,
    exclude_role_contains. Role text is compared case-insensitively.
    """
    known = {"category", "role_contains", "exclude_names", "exclude_role_contains"}
    if set(rule) - known:
        die(f"unknown match keys: {sorted(set(rule) - known)}")

    def match(t: dict) -> bool:
        role = t["speaker_role"].lower()
        if "category" in rule and cats.get((t["speaker_name"], t["speaker_role"])) != rule["category"]:
            return False
        if "role_contains" in rule and rule["role_contains"].lower() not in role:
            return False
        if t["speaker_name"] in rule.get("exclude_names", ()):
            return False
        return not any(x.lower() in role for x in rule.get("exclude_role_contains", ()))

    return match


def person_matcher(name: str):
    return lambda t: t["speaker_name"] == name


# ---- text -----------------------------------------------------------------------------------
@functools.lru_cache(maxsize=8)
def _join_patterns(joins: tuple[tuple[str, str], ...]) -> tuple[tuple[re.Pattern, str], ...]:
    ordered = sorted(joins, key=lambda kv: -len(kv[0]))
    return tuple((re.compile(r"\b" + re.escape(k) + r"\b"), v) for k, v in ordered)


def tokens(text: str, joins: tuple[tuple[str, str], ...] = ()) -> list[str]:
    """Lowercase words. Drops possessive 's, splits hyphenated words ("self-improvement" ->
    "self improvement"), then rewrites each multi-word term in joins to one token."""
    s = HYPHEN.sub(" ", POSSESSIVE.sub("", text.lower().replace("’", "'")))
    for pattern, token in _join_patterns(joins):
        s = pattern.sub(token, s)
    return TOKEN.findall(s)


def build_stopwords(cfg: dict, speakers: list[dict]) -> set[str]:
    stop = set(cfg["stopwords"])
    names = {w for s in speakers for w in re.findall(r"[a-z]+", s["speaker_name"].lower())}
    return stop | (names - set(cfg["method"]["name_tokens_not_stopped"]))


def grams(text: str, stop: set[str], method: dict) -> list[str]:
    skip_any = set(method["skip_tokens_in_any_gram"])
    skip_exact = {tuple(g.split()) for g in method["skip_exact_grams"]}
    short_ok = set(method["short_tokens_allowed"])
    joins = tuple(sorted(method.get("join_terms", {}).items()))
    out = []
    for sentence in SENTENCE_SPLIT.split(text):
        w = tokens(sentence, joins)
        for n in range(1, method["max_ngram"] + 1):
            for i in range(len(w) - n + 1):
                g = w[i:i + n]
                if skip_any.intersection(g) or tuple(g) in skip_exact:
                    continue
                if g[0] in stop or g[-1] in stop:
                    continue
                if n > 1 and sum(x in stop for x in g) > n // 2:
                    continue
                if any(len(x) < 3 and x not in short_ok for x in (g[0], g[-1])):
                    continue
                out.append(" ".join(g))
    return out


def score(turns: list[dict], in_group, stop: set[str], method: dict, min_count: int) -> dict:
    """Weighted log-odds (informative Dirichlet prior), group vs everyone else."""
    a, b = collections.Counter(), collections.Counter()
    for t in turns:
        (a if in_group(t) else b).update(grams(t["text_clean"], stop, method))
    n_a, n_b = sum(a.values()), sum(b.values())
    if not n_a:
        die("group has no words after filtering")
    pooled = a + b
    n_p = n_a + n_b
    a0 = n_p * method["prior_scale"]
    res = []
    for g, ca in a.items():
        if ca < min_count:
            continue
        cb = b[g]
        ap = pooled[g] / n_p * a0
        delta = math.log((ca + ap) / (n_a + a0 - ca - ap)) - math.log((cb + ap) / (n_b + a0 - cb - ap))
        z = delta / math.sqrt(1 / (ca + ap) + 1 / (cb + ap))
        if z > method["z_threshold"]:
            res.append({"phrase": g, "group_count": ca, "others_count": cb, "z": round(z, 2),
                        "n": len(g.split())})
    res.sort(key=lambda r: -r["z"])
    ratio = method["subsume_ratio"]
    keep = [r for r in res if not any(
        f" {r['phrase']} " in f" {k['phrase']} " and k["n"] > r["n"] and k["group_count"] >= ratio * r["group_count"]
        for k in res)]
    return {"phrases": keep, "n_group": n_a, "n_others": n_b}


def turn_stats(turns: list[dict], in_group) -> dict:
    mine = [t for t in turns if in_group(t)]
    return {"speakers": collections.Counter(t["speaker_name"] for t in mine), "turns": len(mine),
            "minutes": round(sum(float(t["end_sec"]) - float(t["start_sec"]) for t in mine) / 60, 1),
            "words": sum(len(tokens(t["text_clean"])) for t in mine)}


def display(phrase: str, cap: dict[str, str]) -> str:
    return cap.get(phrase, " ".join(cap.get(w, w) for w in phrase.split()))


def long_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def hours_phrase(hms: str) -> str:
    h, m, s = (int(x) for x in hms.split(":"))
    return f"{round(h + m / 60 + s / 3600)}-hour"


# ---- html -----------------------------------------------------------------------------------
STYLE = """
:root { --blue:#2359a8; --text:#414141; --muted:#595959; --border:#949494; --grid:#e6e6e6; --bg-blue:#EEF4FF; }
* { box-sizing:border-box; }
body { margin:0; font-family:Poppins, sans-serif; font-size:17px; line-height:30px; color:var(--text); background:#fff; }
.wrap { max-width:1230px; margin:0 auto; padding:0 max(1.25rem, 5vw); }
header.site { border-bottom:1px solid var(--border); padding:16px 0; }
header.site img { height:48px; width:auto; display:block; }
h1 { font-family:Poppins, sans-serif; font-weight:700; font-size:clamp(30px, 4.5vw, 44px); line-height:1.3; color:#000; margin:24px 0 8px; }
h2, h3 { font-family:Roboto, sans-serif; font-weight:700; color:#000; }
h2 { font-size:24px; line-height:34px; margin:0 0 8px; }
h3 { font-size:20px; line-height:30px; margin:0 0 8px; }
a { color:var(--blue); text-decoration:underline; }
a:focus-visible, summary:focus-visible { outline:3px solid var(--blue); outline-offset:2px; }
.crumbs { font-size:15px; margin:16px 0 0; }
nav.groups ul { list-style:none; padding:0; margin:16px 0 0; display:flex; flex-wrap:wrap; gap:8px; }
nav.groups a { display:inline-block; border:1px solid var(--border); padding:2px 14px; text-decoration:none; }
nav.groups a:hover { background:var(--bg-blue); }
nav.groups a[aria-current="page"] { background:var(--blue); color:#fff; border-color:var(--blue); font-weight:700; }
.sub { color:var(--muted); font-size:15px; line-height:24px; margin:0 0 8px; max-width:900px; }
.card { border:1px solid var(--border); border-radius:0; padding:24px; margin:24px 0; background:#fff; }
.note { font-size:15px; line-height:24px; color:var(--muted); margin:0 0 12px; }
.brief { background:var(--bg-blue); padding:12px 20px; max-width:750px; }
svg.cloud { width:100%; height:auto; display:block; }
svg.cloud text { cursor:default; }
svg.cloud text:hover, svg.cloud text:focus { text-decoration:underline; outline:none; }
svg.bars { width:100%; height:auto; display:block; }
svg.bars g.bar:hover path.mark, svg.bars g.bar:focus path.mark { fill:#1b467f; }
svg.bars g.bar:focus { outline:none; }
svg.bars g.bar:focus text.lab { text-decoration:underline; }
.tip { position:fixed; pointer-events:none; background:#fff; color:var(--text); border:1px solid var(--border); padding:8px 10px; font-size:14px; line-height:20px; box-shadow:0 2px 8px rgba(0,0,0,.12); display:none; max-width:280px; white-space:pre-line; }
table { border-collapse:collapse; font-size:15px; line-height:22px; }
th, td { border:1px solid var(--border); padding:4px 8px; text-align:left; }
td.num, th.num { text-align:right; }
details { margin:11px 0; }
summary { cursor:pointer; color:var(--blue); }
.how { max-width:750px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:24px; }
.grid .card { margin:0; }
.phrases { padding-left:20px; margin:8px 0; }
footer { border-top:1px solid var(--border); margin-top:54px; padding:24px 0; font-size:15px; }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;700&family=Roboto:wght@400;700'
         '&display=swap" rel="stylesheet">')

PAPER = ('<a href="https://doi.org/10.1093/pan/mpn018">Monroe, Colaresi and Quinn (2008), &ldquo;Fightin&#x27; '
         'Words: Lexical Feature Selection and Evaluation for Identifying the Content of Political '
         'Conflict,&rdquo; <em>Political Analysis</em> 16(4)</a>')

# Word cloud: Archimedean spiral with bounding-box collision, measured with the page font
# after web fonts load. Bars: label and value widths measured first so nothing clips.
SCRIPT = r"""
const NS='http://www.w3.org/2000/svg', tip=document.getElementById('tip');
function plural(n,w){return n+' '+(n===1?w:w+'s')}
function info(p){return p.label+'\n'+SUBJECT+': '+plural(p.n,'time')+'\nEveryone else: '+plural(p.o,'time')}
function show(e,p){tip.textContent=info(p);tip.style.display='block';const r=e.target.getBoundingClientRect();
 const x=(e.clientX||r.left+r.width/2)+14,y=(e.clientY||r.bottom)+14;
 tip.style.left=Math.min(x,innerWidth-290)+'px';tip.style.top=Math.min(y,innerHeight-90)+'px'}
function hide(){tip.style.display='none'}
function wire(el,p){el.addEventListener('mousemove',e=>show(e,p));el.addEventListener('mouseleave',hide);
 el.addEventListener('focus',e=>show(e,p));el.addEventListener('blur',hide)}
function mk(tag,attrs,parent){const el=document.createElementNS(NS,tag);for(const k in attrs)el.setAttribute(k,attrs[k]);if(parent)parent.appendChild(el);return el}
function cloud(){const svg=document.getElementById('cloud');if(!svg||!PH.length)return;
 const W=980,H=PH.length>25?520:380,c=document.createElement('canvas').getContext('2d');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
 const font=getComputedStyle(svg).fontFamily,zs=PH.map(p=>p.z),zmax=Math.max(...zs),zmin=Math.min(...zs);
 function layout(k){const placed=[];PH.forEach((p,i)=>{const s=Math.round((14+(zmax>zmin?Math.sqrt((p.z-zmin)/(zmax-zmin)):1)*48)*k);
  c.font=`700 ${s}px ${font}`;const w=c.measureText(p.label).width+8,h=s*1.12;let t=0,x,y;
  while(t<6000){const a=0.35*t,r=2.2*a;x=W/2+r*Math.cos(a)*1.6-w/2;y=H/2+r*Math.sin(a)-h/2;t++;
   if(x<4||y<4||x+w>W-4||y+h>H-4)continue;
   if(!placed.some(b=>x<b.x+b.w&&x+w>b.x&&y<b.y+b.h&&y+h>b.y)){placed.push({x,y,w,h,s,p,i});return}}});return placed}
 // shrink every word together until all fit (or stop at 60%); the table lists any that still do not
 let k=1,placed=layout(k);while(placed.length<PH.length&&k>0.62){k-=0.06;placed=layout(k)}
 placed.forEach(({x,y,h,s,p,i})=>{
  const el=mk('text',{x:x+4,y:y+h*0.8,'font-size':s,'font-weight':700,fill:i<HL?'#2359a8':'#414141',tabindex:0,
   'aria-label':`${p.label}: rank ${i+1} of ${PH.length}; ${SUBJECT} ${plural(p.n,'time')}, everyone else ${plural(p.o,'time')}`},svg);
  el.textContent=p.label;wire(el,p)})}
function bars(){const svg=document.getElementById('bars');if(!svg||!BARS.length)return;
 const c=document.createElement('canvas').getContext('2d'),font=getComputedStyle(svg).fontFamily;
 c.font=`14px ${font}`;const L=Math.ceil(Math.max(...BARS.map(b=>c.measureText(b.label).width)))+16;
 c.font=`13px ${font}`;const tails=BARS.map(b=>({v:plural(b.n,'time'),o:` (everyone else: ${b.o})`}));
 const R=Math.ceil(Math.max(...tails.map(t=>c.measureText(t.v+t.o).width)))+18;
 const rowH=28,bh=18,W=980,H=BARS.length*rowH+30;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
 const span=W-L-R,max=Math.max(...BARS.map(b=>b.n)),sx=v=>v/max*span,step=max<=4?1:Math.ceil(max/4);
 for(let v=step;v<=max;v+=step){const gx=L+sx(v);mk('line',{x1:gx,x2:gx,y1:0,y2:H-24,stroke:'#e6e6e6'},svg);
  mk('text',{x:gx,y:H-6,'text-anchor':'middle','font-size':12,fill:'#595959'},svg).textContent=v}
 mk('line',{x1:L,x2:L,y1:0,y2:H-24,stroke:'#949494'},svg);
 BARS.forEach((b,i)=>{const y=i*rowH+5,g=mk('g',{class:'bar',tabindex:0,
   'aria-label':`${b.label}: ${SUBJECT} ${plural(b.n,'time')}, everyone else ${plural(b.o,'time')}`},svg);
  mk('rect',{x:0,y:y-5,width:W,height:rowH,fill:'transparent'},g);
  mk('text',{class:'lab',x:L-8,y:y+bh-4,'text-anchor':'end','font-size':14,fill:'#414141'},g).textContent=b.label;
  const w=Math.max(5,sx(b.n));
  mk('path',{class:'mark',fill:'#2359a8',d:`M${L},${y} h${w-4} a4,4 0 0 1 4,4 v${bh-8} a4,4 0 0 1 -4,4 h${-(w-4)} z`},g);
  const v=mk('text',{x:L+w+6,y:y+bh-4,'font-size':13,fill:'#414141'},g);
  mk('tspan',{},v).textContent=tails[i].v;mk('tspan',{fill:'#595959'},v).textContent=tails[i].o;wire(g,b)})}
(document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(()=>{cloud();bars()});
"""


def site_header(root: str) -> str:
    return (f'<a href="#main" class="note" style="position:absolute;left:-999px" '
            f'onfocus="this.style.left=\'8px\'" onblur="this.style.left=\'-999px\'">Skip to content</a>\n'
            f'<header class="site"><div class="wrap"><a href="https://beta.nyc/"><img src="{root}assets/'
            f'betanyc-logo.svg" alt="BetaNYC home" width="142" height="48"></a></div></header>')


def footer(root: str) -> str:
    return (f'<footer><div class="wrap">BetaNYC · <a href="https://beta.nyc/">beta.nyc</a> · '
            f'<a href="{root}index.html">All hearing transcripts</a> · '
            f'<a href="{root}README.md">About this repository</a></div></footer>')


def group_nav(groups: list[dict], current: str | None, prefix: str) -> str:
    cur = ' aria-current="page"'
    items = "".join(
        f'<li><a href="{prefix}{esc(g["slug"])}.html"{cur if g["slug"] == current else ""}>'
        f'{esc(g["nav"])}</a></li>'
        for g in groups)
    return f'<nav class="groups" aria-label="Speaker groups"><ul>{items}</ul></nav>'


def json_for_script(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


CONFIG_URL = "https://github.com/BetaNYC/hearings-transcripts/blob/main/scripts/meta/wordclouds.json"
REMOVED = ("Common words, speakers&#x27; names, &ldquo;New York&rdquo;, &ldquo;city&rdquo;, &ldquo;AI&rdquo; and "
           "hearing boilerplate are left out. Beyond a standard list of common words, filler (polite forms, "
           "connecting words, generic verbs) was removed by hand: an AI assistant, working at BetaNYC&#x27;s "
           "direction, reviewed each group&#x27;s and each person&#x27;s list and proposed the cuts. The full "
           f'list of removed words is in <a href="{CONFIG_URL}">scripts/meta/wordclouds.json</a>.')
JOINED = ("&ldquo;super intelligent&rdquo; as &ldquo;superintelligent&rdquo;, &ldquo;kill switches&rdquo; as "
          "&ldquo;kill switch&rdquo;, &ldquo;open-weight&rdquo; and &ldquo;affected parties&rdquo; as one term")


def how_made(subject_kind: str, min_count: int, csv_name: str, root: str) -> str:
    if subject_kind == "person":
        base = ("this speaker said much more often than everyone else at the hearing, including the "
                "rest of their own group")
        who_rule = ("Turns are assigned to a speaker by the speaker labels, which were assigned by AI agents "
                    "working from self-introductions, the chair calling on people, and voice clusters, at "
                    "BetaNYC&#x27;s direction. A mislabeled turn counts toward the wrong speaker.")
    else:
        base = "this group said much more often than all other speakers at the hearing"
        who_rule = ("Speaker groups come from the speaker labels, which were assigned by AI agents working "
                    "from self-introductions, the chair calling on people, and voice clusters, at BetaNYC&#x27;s "
                    "direction. Each label&#x27;s role sets its group. A mislabeled turn counts toward the "
                    "wrong group.")
    return f"""<section class="how" aria-labelledby="how">
<h2 id="how">How this was made</h2>
<ul>
<li><strong>&ldquo;Distinctive&rdquo;</strong> means a phrase {base}, after allowing for how much each side talked. A phrase someone says often but everyone else also says often is not distinctive.</li>
<li>Each phrase gets a score from the &ldquo;weighted log-odds&rdquo; test in {PAPER}. We keep phrases said at least {min_count} times with a score above 1.96, a common cutoff; with thousands of phrases tested, a few may pass by chance, so read the list as a guide, not proof. When a short phrase almost always appears inside a longer one, only the longer one is shown.</li>
<li>Counts are how many times each 1- to 3-word phrase occurs in the clean verbatim transcript. Hyphenated words are counted as separate words (&ldquo;self-improvement&rdquo; is &ldquo;self improvement&rdquo;), and a few terms the transcript spells more than one way are counted as one ({JOINED}).</li>
<li>{REMOVED}</li>
<li>{who_rule}</li>
<li>This is a machine transcript, not an official record. Check the video before quoting anyone; search <a href="{root}transcript/transcript-clean.txt">the clean transcript</a> to find where a phrase was said.</li>
<li>Data: <a href="{esc(csv_name)}" download>{esc(csv_name)}</a> (every phrase that passed). Code: <code>scripts/build_wordclouds.py</code>.</li>
</ul>
</section>"""


def render_page(*, hearing: dict, groups: list[dict], current_group: str | None, title_who: str, subline: str,
                extra: str, result: dict, stats: dict, display_cfg: dict, cap: dict, subject: str,
                subject_kind: str, min_count: int, csv_name: str, root: str, hearing_root: str,
                nav_prefix: str, gallery_href: str) -> str:
    phrases = result["phrases"]
    ph = phrases[:display_cfg["cloud_phrases"]]
    for x in ph:
        x["label"] = display(x["phrase"], cap)
    bars = sorted(ph[:display_cfg["bar_phrases"]], key=lambda x: (-x["group_count"], x["label"].lower()))
    hl = display_cfg["highlighted_phrases"]
    top_list = ", ".join(x["label"] for x in ph[:hl])
    rows = "".join(f"<tr><td>{esc(x['label'])}</td><td class=\"num\">{x['group_count']}</td>"
                   f"<td class=\"num\">{x['others_count']}</td><td class=\"num\">{x['z']:.2f}</td></tr>" for x in ph)
    js_ph = [{"label": x["label"], "n": x["group_count"], "o": x["others_count"], "z": x["z"]} for x in ph]
    js_bars = [{"label": x["label"], "n": x["group_count"], "o": x["others_count"]} for x in bars]
    hearing_name = f"{hearing['body']}, {long_date(hearing['date'])}"
    hours = hours_phrase(hearing["video"]["duration_hms"])
    subject_col = "This group" if subject_kind == "group" else esc(subject)
    if ph:
        charts = f"""<section class="card" aria-labelledby="cloud-h">
<h2 id="cloud-h">Phrases {esc(title_who)} used far more than everyone else</h2>
<p class="note">Bigger means more distinctive: used often here, rarely by everyone else. The {min(hl, len(ph))} most distinctive are blue and largest. Hover or tab to a phrase for its counts. The full list is in the table below.</p>
<svg id="cloud" class="cloud" viewBox="0 0 980 520" role="group" aria-labelledby="cloud-t cloud-d" xmlns="http://www.w3.org/2000/svg"><title id="cloud-t">Word cloud of the {len(ph)} most distinctive phrases</title><desc id="cloud-d">Most distinctive first: {esc(", ".join(x["label"] for x in ph))}.</desc></svg>
</section>
<section class="card" aria-labelledby="bars-h">
<h2 id="bars-h">How many times {esc(title_who)} said it</h2>
<p class="note">The {len(bars)} most distinctive phrases, ordered by how many times {esc(title_who)} said each one in about {stats['minutes']} minutes of talk. The gray number in parentheses is how many times everyone else said it across the rest of the {hours} hearing.</p>
<svg id="bars" class="bars" viewBox="0 0 980 600" role="group" aria-labelledby="bars-t bars-d" xmlns="http://www.w3.org/2000/svg"><title id="bars-t">Bar chart: times said, with everyone else&#x27;s count</title><desc id="bars-d">{esc("; ".join(f"{x['label']}: {x['group_count']}, everyone else {x['others_count']}" for x in bars))}.</desc></svg>
<details><summary>Show the data as a table</summary>
<table><caption>{len(ph)} most distinctive phrases, most distinctive first</caption>
<thead><tr><th scope="col">Phrase</th><th scope="col" class="num">{subject_col}</th><th scope="col" class="num">Everyone else</th><th scope="col" class="num">Distinctiveness score</th></tr></thead>
<tbody>{rows}</tbody></table></details>
</section>"""
    else:
        charts = '<p class="brief">No phrase passed the test, so there is no word cloud.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What {esc(title_who)} talked about · {esc(hearing_name)} · BetaNYC</title>
<meta name="description" content="Phrases {esc(title_who)} used far more than anyone else at the {esc(hearing_name)} hearing. Most distinctive: {esc(top_list)}.">
{FONTS}
<style>{STYLE}</style>
</head>
<body>
{site_header(root)}
<main id="main" class="wrap">
<p class="crumbs"><a href="{root}index.html#h-{esc(hearing['slug'])}">{esc(hearing_name)}</a> › <a href="{gallery_href}">What each group talked about</a></p>
{group_nav(groups, current_group, nav_prefix)}
<h1>What {esc(title_who)} talked about</h1>
<p class="sub">{subline}</p>
{extra}
{charts}
{how_made(subject_kind, min_count, csv_name, hearing_root)}
</main>
{footer(root)}
<div class="tip" id="tip" aria-hidden="true"></div>
<script>
const SUBJECT={json_for_script(subject)}, HL={hl};
const PH={json_for_script(js_ph)};
const BARS={json_for_script(js_bars)};
{SCRIPT}</script>
</body>
</html>
"""


def speaker_line(speakers: collections.Counter) -> str:
    sp = [f"{k} ({plural(v, 'turn')})" for k, v in sorted(speakers.items(), key=lambda kv: -kv[1])
          if not k.startswith("Unidentified")]
    unid = sum(v for k, v in speakers.items() if k.startswith("Unidentified"))
    line = ", ".join(sp) if len(sp) <= 8 else ", ".join(sp[:6]) + f" and {len(sp) - 6} others"
    return line + (f", plus {plural(unid, 'unidentified turn')}" if unid else "")


def stats_line(stats: dict) -> str:
    return f"{plural(stats['turns'], 'turn')}, about {stats['minutes']} minutes, {plural(stats['words'], 'word')}"


def gallery_card(title: str, note: str, href: str, phrases: list[dict], cap: dict, n: int, hid: str) -> str:
    items = "".join(f"<li>{esc(display(x['phrase'], cap))}</li>" for x in phrases[:n])
    body = f'<ol class="phrases">{items}</ol>' if items else '<p class="note">No phrase passed the test.</p>'
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    return (f'<article class="card" aria-labelledby="{hid}"><h3 id="{hid}">{esc(title)}</h3>{note_html}'
            f'<p class="note">Most distinctive phrases:</p>{body}'
            f'<p><a href="{esc(href)}">See the word cloud and counts for {esc(title)}</a></p></article>')


def qa_link(slug: str, prefix: str) -> str:
    """Pointer to the City Q&A page, if build_qa.py has made one."""
    if not (REPO / "hearings" / slug / "city-qa.html").is_file():
        return ""
    return (f'<p class="brief"><a href="{prefix}city-qa.html">Read every '
            f'question Council Members asked the City, and the administration&#x27;s answers</a>.</p>')


def render_gallery(hearing: dict, group_cards: list[str], person_cards: list[str], cfg: dict) -> str:
    hearing_name = f"{hearing['body']}, {long_date(hearing['date'])}"
    root = "../../../"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What each group talked about · {esc(hearing_name)} · BetaNYC</title>
<meta name="description" content="The phrases each group of speakers used far more than everyone else at the {esc(hearing_name)} hearing.">
{FONTS}
<style>{STYLE}</style>
</head>
<body>
{site_header(root)}
<main id="main" class="wrap">
<p class="crumbs"><a href="{root}index.html#h-{esc(hearing['slug'])}">{esc(hearing_name)}</a> › What each group talked about</p>
{group_nav(cfg["groups"], None, "")}
<h1>What each group talked about</h1>
<p class="sub">{esc(hearing['title'])}. For each group of speakers, the phrases they used far more often than everyone else at the hearing. Each page has a word cloud, a bar chart of counts, and the data as a table.</p>
{qa_link(hearing["slug"], "../")}
<section aria-labelledby="groups-h"><h2 id="groups-h">Speaker groups</h2>
<div class="grid">{"".join(group_cards)}</div></section>
{('<section aria-labelledby="people-h" style="margin-top:36px"><h2 id="people-h">Individual speakers</h2><p>' + esc(cfg["people_method"].get("intro", "")) + '</p><p class="note">Each person is compared with everyone else at the hearing, including the rest of their own group. Phrases said at least ' + str(cfg["people_method"]["min_person_count"]) + ' times count, because some spoke only briefly.</p><div class="grid">' + "".join(person_cards) + '</div></section>') if person_cards else ''}
<section class="how" aria-labelledby="how" style="margin-top:36px">
<h2 id="how">How this was made</h2>
<p>&ldquo;Distinctive&rdquo; means a phrase a group said much more often than all other speakers, after allowing for how much each side talked, scored with the weighted log-odds test in {PAPER}. Counts come from the clean verbatim transcript. Groups come from AI-assigned speaker labels. This is a machine transcript; check the video before quoting anyone. Each page explains the details. Code: <code>scripts/build_wordclouds.py</code>.</p>
<p>{REMOVED}</p>
{('<p><strong>' + esc(cfg["gallery_disclosure"]) + '</strong></p>') if cfg.get("gallery_disclosure") else ''}
</section>
</main>
{footer(root)}
</body>
</html>
"""


# ---- build ----------------------------------------------------------------------------------
def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if path.stat().st_size >= MAX_FILE_BYTES:
        die(f"{path} is over 100 MB")


def write_phrase_csv(path: Path, phrases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        w.writeheader()
        for x in phrases:
            w.writerow({"phrase": x["phrase"], "group_count": x["group_count"],
                        "others_count": x["others_count"], "z": f"{x['z']:.2f}"})


def compute(hdir: Path, cfg: dict) -> dict:
    """Score every group and person. Returns {"groups": {slug: (result, stats)}, "people": {...}}."""
    turns = read_csv(hdir / "transcript" / "turns.csv")
    speakers = read_csv(hdir / "speakers.csv")
    cats = category_map(speakers)
    stop = build_stopwords(cfg, speakers)
    out = {"groups": {}, "people": {}, "turns": turns}
    for g in cfg["groups"]:
        m = group_matcher(g["match"], cats)
        st = turn_stats(turns, m)
        if not st["turns"]:
            die(f"group {g['slug']} matches no turns")
        out["groups"][g["slug"]] = (score(turns, m, stop, cfg["method"], cfg["method"]["min_group_count"]), st)
    names = {s["speaker_name"] for s in speakers}
    for p in cfg["people"]:
        if p["name"] not in names:
            die(f"person {p['name']!r} is not in speakers.csv")
        m = person_matcher(p["name"])
        out["people"][p["slug"]] = (score(turns, m, stop, cfg["method"], cfg["people_method"]["min_person_count"]),
                                    turn_stats(turns, m))
    return out


def build(slug: str, cfg: dict) -> None:
    hdir = REPO / "hearings" / slug
    hearing = json.loads((hdir / "hearing.json").read_text(encoding="utf-8"))
    res = compute(hdir, cfg)
    wdir = hdir / "wordclouds"
    disp, cap = cfg["display"], cfg["capitalization"]
    people_by_group = collections.defaultdict(list)
    for p in cfg["people"]:
        people_by_group[p["group"]].append(p)
    gcards, pcards = [], []
    for g in cfg["groups"]:
        result, st = res["groups"][g["slug"]]
        bits = [esc(x) for x in (speaker_line(st["speakers"]), g["note"], stats_line(st), g.get("disclosure", "")) if x]
        sub = " · ".join(bits)
        ppl = people_by_group.get(g["slug"], [])
        extra = ""
        if ppl:
            links = ", ".join(f'<a href="people/{esc(p["slug"])}.html">{esc(p["name"])} ({esc(p["affiliation"])})</a>'
                              if p["affiliation"] != "Whistleblower panel" else
                              f'<a href="people/{esc(p["slug"])}.html">{esc(p["name"])}</a>' for p in ppl)
            extra = f'<p>Each speaker in this group on their own: {links}.</p>'
        if g["slug"] == "city-officials":
            extra += qa_link(slug, "../")
        page = render_page(hearing=hearing, groups=cfg["groups"], current_group=g["slug"], title_who=g["who"],
                           subline=sub, extra=extra, result=result, stats=st, display_cfg=disp, cap=cap,
                           subject="This group", subject_kind="group",
                           min_count=cfg["method"]["min_group_count"], csv_name=f"{g['slug']}.csv",
                           root="../../../", hearing_root="../", nav_prefix="", gallery_href="index.html")
        write_text(wdir / f"{g['slug']}.html", page)
        write_phrase_csv(wdir / f"{g['slug']}.csv", result["phrases"])
        title = g["who"][0].upper() + g["who"][1:]
        gcards.append(gallery_card(title, g["note"], f"{g['slug']}.html", result["phrases"], cap,
                                   disp["gallery_phrases"], f"g-{g['slug']}"))
        log("group_written", group=g["slug"], turns=st["turns"], phrases=len(result["phrases"]))
    gmap = {g["slug"]: g for g in cfg["groups"]}
    pm = cfg["people_method"]
    for p in cfg["people"]:
        result, st = res["people"][p["slug"]]
        grp = gmap[p["group"]]
        sub = esc(f"{p['affiliation']} · {stats_line(st)}")
        extra = (f'<p>Part of <a href="../{esc(grp["slug"])}.html">{esc(grp["who"])}</a>. '
                 f'Compared with everyone else at the hearing, including the rest of the group.</p>')
        if len(result["phrases"]) < pm["brief_threshold"]:
            extra += (f'<p class="brief">{esc(p["name"])} spoke for about {st["minutes"]} minutes, so only '
                      f'{plural(len(result["phrases"]), "phrase")} passed the test. The list is short because '
                      f'the time was short, not because the remarks were.</p>')
        page = render_page(hearing=hearing, groups=cfg["groups"], current_group=None, title_who=p["name"],
                           subline=sub, extra=extra, result=result, stats=st, display_cfg=disp, cap=cap,
                           subject=p["name"], subject_kind="person", min_count=pm["min_person_count"],
                           csv_name=f"{p['slug']}.csv", root="../../../../", hearing_root="../../",
                           nav_prefix="../", gallery_href="../index.html")
        write_text(wdir / "people" / f"{p['slug']}.html", page)
        write_phrase_csv(wdir / "people" / f"{p['slug']}.csv", result["phrases"])
        pcards.append(gallery_card(f"{p['name']} ({p['affiliation']})", "", f"people/{p['slug']}.html",
                                   result["phrases"], cap, disp["gallery_phrases"], f"p-{p['slug']}"))
        log("person_written", person=p["slug"], turns=st["turns"], phrases=len(result["phrases"]))
    write_text(wdir / "index.html", render_gallery(hearing, gcards, pcards, cfg))
    log("gallery_written", slug=slug, groups=len(gcards), people=len(pcards))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", action="append", help="hearing slug (repeatable); default: every hearing")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    a = ap.parse_args(argv)
    cfg_path = Path(a.config)
    if not cfg_path.is_file():
        die(f"config missing: {cfg_path}")
    cfg = load_config(cfg_path)
    slugs = a.slug or sorted(p.parent.parent.name for p in (REPO / "hearings").glob("*/transcript/turns.csv"))
    if not slugs:
        die("no hearings with transcript/turns.csv")
    for slug in slugs:
        build(slug, cfg)


if __name__ == "__main__":
    main()
