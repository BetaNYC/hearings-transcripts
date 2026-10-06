#!/usr/bin/env python3
"""Build the public exports for one NYC Council hearing, then rebuild index.html.

Pure standard library. Tested range: Python 3.11 to 3.14.

Inputs (all local files):
  --meta            hand-written hearing metadata (scripts/meta/<slug>.json)
  --deepgram        Deepgram intermediate JSON: {segments:[{start,end,speaker,text,
                    words:[{w,s,e}]}], duration_sec, model}
  --labels          speaker labels JSON: list indexed by turn id,
                    {i,name,role,confidence,evidence}
  --transcript      unedited transcript text  ([HH:MM:SS] Name: text, one turn per block)
  --transcript-clean  clean-verbatim transcript text (same turns, same prefixes)
  --audio-opus      optional: Opus audio to copy into media/ (must be < 100 MB)
  --legistar-pre-readme / --legistar-pre-dir / --legistar-post-json / --legistar-post-dir
                    optional: rebuild legistar/ (documents + manifest.csv).
                    If omitted, the existing legistar/manifest.csv is kept.

  python3 scripts/build_hearing.py --index-only     rebuilds index.html only.

A "turn" is a run of consecutive Deepgram segments with the same speaker cluster
and a gap under 5 seconds between them. Turn ids are 0-based and match the
speaker-labels index. The script refuses to write anything if the turn count,
the [HH:MM:SS] prefixes, or the speaker names in either transcript disagree.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import itertools
import json
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAP_SEC = 5.0
MAX_CUE_SEC = 7.0
MAX_LINE = 42
MAX_FILE_BYTES = 100 * 1024 * 1024  # GitHub hard limit per file
VALID_CONFIDENCE = ("high", "medium", "low")

TURN_FIELDS = [
    "turn_id", "start_sec", "end_sec", "start_hms", "end_hms", "speaker_name",
    "speaker_role", "confidence", "deepgram_cluster", "text_clean", "text_unedited",
]
SPEAKER_FIELDS = ["speaker_name", "speaker_role", "category", "turns", "talk_seconds", "first_heard_hms"]
MANIFEST_FIELDS = ["matter_file", "matter_title", "attachment_name", "legistar_url",
                   "last_modified_utc", "filename", "bytes"]

# ---- speaker categories ---------------------------------------------------------
# Derived from the label's role (and name, for unidentified speakers). Documented in README.md.
CATEGORIES = {
    "council": ("Council Member or Speaker", "#2359a8"),
    "council-staff": ("Council staff", "#5a6b80"),
    "city-official": ("City official", "#1b7a5a"),
    "state-or-other-elected": ("State or other elected", "#7a3e9d"),
    "ai-company": ("AI company", "#b5470f"),
    "witness": ("Other witness", "#8a6d00"),
    "unidentified": ("Unidentified", "#6f6f6f"),
}
COUNCIL_ROLES = {"Speaker", "Council Member"}
COUNCIL_STAFF_ROLES = {"Committee Counsel", "Sergeant-at-Arms"}
ELECTED_ROLE_PREFIXES = ("NY State Senator", "NY State Assembly Member", "NYC Public Advocate",
                         "UK Member of Parliament")
WITNESS_PREFIX = "Witness — "
AI_COMPANY_ORGS = {"openai", "anthropic", "meta", "google", "company panel"}
CITY_AGENCY_ORGS = {"oti", "nyc cyber command / oti", "dcwp", "nyc emergency management",
                    "nyc equal employment practices commission"}
ELECTED_WITNESS_ORGS = {"ny state senate"}


def categorize(name: str, role: str) -> str:
    if role == "Unidentified" or name.startswith("Unidentified"):
        return "unidentified"
    if role in COUNCIL_ROLES:
        return "council"
    if role in COUNCIL_STAFF_ROLES:
        return "council-staff"
    if role.startswith(ELECTED_ROLE_PREFIXES):
        return "state-or-other-elected"
    if role.startswith(WITNESS_PREFIX):
        org = role[len(WITNESS_PREFIX):].strip().lower()
        if org in AI_COMPANY_ORGS:
            return "ai-company"
        if org in CITY_AGENCY_ORGS:
            return "city-official"
        if org in ELECTED_WITNESS_ORGS:
            return "state-or-other-elected"
        return "witness"
    raise ValueError(f"No category rule for role {role!r} (speaker {name!r}); add one to build_hearing.py")


# ---- small helpers ------------------------------------------------------------------
def log(event: str, **kw) -> None:
    parts = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} build_hearing {event} {parts}".rstrip(), file=sys.stderr)


def die(msg: str) -> None:
    log("error", msg=json.dumps(msg))
    sys.exit(1)


def hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def vtt_ts(sec: float) -> str:
    ms = round(sec * 1000)
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d}.{ms % 1000:03d}"


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


ARCHIVE_PENDING_NOTE = "The Internet Archive upload is still in progress; the item may not be playable yet."
RELEASE_PENDING_NOTE = "The GitHub Release may not exist yet."


def archive_note(meta: dict) -> str:
    """Caveat shown until meta video.archive_playable is set true."""
    return "" if meta["video"].get("archive_playable") else ARCHIVE_PENDING_NOTE


def release_note(meta: dict) -> str:
    """Caveat shown until meta media.audio_mp3.release_published is set true."""
    return "" if meta["media"]["audio_mp3"].get("release_published") else RELEASE_PENDING_NOTE


def human_dur(sec: float) -> str:
    m = round(sec / 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    write_text(path, buf.getvalue())


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- turns ----------------------------------------------------------------------------
def merge_turns(segments: list[dict]) -> list[dict]:
    turns: list[dict] = []
    for seg in segments:
        if turns and turns[-1]["cluster"] == seg["speaker"] and seg["start"] - turns[-1]["end"] < GAP_SEC:
            turns[-1]["end"] = max(turns[-1]["end"], seg["end"])
            turns[-1]["segments"].append(seg)
        else:
            turns.append({"cluster": seg["speaker"], "start": seg["start"], "end": seg["end"], "segments": [seg]})
    return turns


TURN_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] ")


def parse_transcript(path: Path) -> list[tuple[str, str]]:
    """Return [(hms, 'Name[ [?]]: text'), ...] for each turn block, skipping the header."""
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
    out = []
    for b in blocks:
        b = b.strip("\n")
        m = TURN_LINE.match(b)
        if m:
            out.append((m.group(1), " ".join(line.strip() for line in b[m.end():].splitlines())))
    return out


def display_name(name: str, role: str, confidence: str) -> str:
    """The speaker string the transcripts print before the colon."""
    if role == "Speaker":
        d = f"Speaker {name}"
    elif role == "Council Member":
        d = f"CM {name}"
    elif role.startswith(WITNESS_PREFIX):
        d = f"{name} ({role[len(WITNESS_PREFIX):]})"
    elif role != name:
        d = f"{name} ({role})"
    else:
        d = name
    return d + (" [?]" if confidence == "low" else "")


def split_turn_text(rest: str, label: dict, which: str, i: int) -> str:
    display = display_name(label["name"], label["role"], label["confidence"])
    prefix = display + ": "
    if not rest.startswith(prefix):
        die(f"{which} turn {i}: expected speaker {display!r}, got {rest[:60]!r}")
    return rest[len(prefix):]


def build_turns(dg: dict, labels: list[dict], t_unedited: Path, t_clean: Path) -> list[dict]:
    raw = merge_turns(dg["segments"])
    if len(raw) != len(labels):
        die(f"turn count {len(raw)} != label count {len(labels)}")
    unedited, clean = parse_transcript(t_unedited), parse_transcript(t_clean)
    for which, parsed in (("unedited", unedited), ("clean", clean)):
        if len(parsed) != len(raw):
            die(f"{which} transcript has {len(parsed)} turns, expected {len(raw)}")
    turns = []
    for i, (t, lab) in enumerate(zip(raw, labels)):
        if lab["i"] != i:
            die(f"label index {lab['i']} at position {i}")
        if lab["confidence"] not in VALID_CONFIDENCE:
            die(f"turn {i}: bad confidence {lab['confidence']!r}")
        for which, parsed in (("unedited", unedited), ("clean", clean)):
            if parsed[i][0] != hms(t["start"]):
                die(f"{which} turn {i}: prefix {parsed[i][0]} != computed {hms(t['start'])}")
        turns.append({
            "turn_id": i,
            "start_sec": round(t["start"], 3),
            "end_sec": round(t["end"], 3),
            "start_hms": hms(t["start"]),
            "end_hms": hms(t["end"]),
            "speaker_name": lab["name"],
            "speaker_role": lab["role"],
            "confidence": lab["confidence"],
            "deepgram_cluster": t["cluster"],
            "text_clean": split_turn_text(clean[i][1], lab, "clean", i),
            "text_unedited": split_turn_text(unedited[i][1], lab, "unedited", i),
            "_segments": t["segments"],
        })
    return turns


def public_turn(t: dict) -> dict:
    return {k: t[k] for k in TURN_FIELDS}


# ---- words + captions ----------------------------------------------------------------
def build_words(turns: list[dict]) -> list[dict]:
    return [{"turn_id": t["turn_id"], "word": w["w"], "start": w["s"], "end": w["e"]}
            for t in turns for seg in t["_segments"] for w in seg.get("words", [])]


def two_lines(text: str) -> str:
    if len(text) <= MAX_LINE:
        return text
    mid = len(text) // 2
    spaces = [m.start() for m in re.finditer(" ", text)]
    if not spaces:
        return text
    cut = min(spaces, key=lambda p: abs(p - mid))
    return text[:cut] + "\n" + text[cut + 1:]


def build_cues(turns: list[dict]) -> list[dict]:
    cues: list[dict] = []
    for t in turns:
        voice = display_name(t["speaker_name"], t["speaker_role"], t["confidence"])
        for seg in t["_segments"]:
            words = seg.get("words") or []
            if not words:
                if seg["text"].strip():
                    cues.append({"start": seg["start"], "end": seg["end"], "voice": voice, "text": seg["text"].strip()})
                continue
            chunk: list[dict] = []
            for w in words:
                candidate = " ".join(x["w"] for x in chunk + [w])
                if chunk and (w["e"] - chunk[0]["s"] > MAX_CUE_SEC or len(candidate) > 2 * MAX_LINE):
                    cues.append({"start": chunk[0]["s"], "end": chunk[-1]["e"], "voice": voice,
                                 "text": " ".join(x["w"] for x in chunk)})
                    chunk = []
                chunk.append(w)
            cues.append({"start": chunk[0]["s"], "end": chunk[-1]["e"], "voice": voice,
                         "text": " ".join(x["w"] for x in chunk)})
    cues.sort(key=lambda c: c["start"])
    for a, b in itertools.pairwise(cues):  # no overlaps: a cue ends no later than the next begins
        a["end"] = min(a["end"], b["start"])
    for c in cues:
        if c["end"] <= c["start"]:
            c["end"] = c["start"] + 0.01
    return cues


def render_vtt(cues: list[dict], meta: dict) -> str:
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = ["WEBVTT", "",
           "NOTE",
           f"{meta['body']}: {meta['title']}, {meta['date']}.",
           "Machine transcript (Deepgram Nova-3), unedited words with their real timings.",
           "Speaker names assigned by BetaNYC; [?] = low confidence. Not an official record.",
           "Transcript data CC BY 4.0, BetaNYC. https://github.com/BetaNYC/hearings-transcripts", ""]
    for n, c in enumerate(cues, 1):
        out += [str(n), f"{vtt_ts(c['start'])} --> {vtt_ts(c['end'])}",
                f"<v {esc(c['voice'])}>{esc(two_lines(c['text']))}", ""]
    return "\n".join(out)


# ---- speakers -------------------------------------------------------------------------
def build_speakers(turns: list[dict]) -> list[dict]:
    agg: dict[tuple[str, str], dict] = {}
    for t in turns:
        key = (t["speaker_name"], t["speaker_role"])
        a = agg.setdefault(key, {"speaker_name": key[0], "speaker_role": key[1],
                                 "category": categorize(*key), "turns": 0, "talk_seconds": 0.0,
                                 "first_heard_hms": t["start_hms"]})
        a["turns"] += 1
        a["talk_seconds"] += t["end_sec"] - t["start_sec"]
    rows = sorted(agg.values(), key=lambda r: -r["talk_seconds"])
    for r in rows:
        r["talk_seconds"] = round(r["talk_seconds"], 2)
    return rows


# ---- legistar ---------------------------------------------------------------------------
README_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]*?)\s*\|\s*`([^`]+)`")


def build_legistar(meta: dict, out: Path, pre_readme: Path, pre_dir: Path, post_json: Path, post_dir: Path) -> list[dict]:
    titles = {b["file"]: b["name"] for b in meta["bills"]}
    titles[meta["oversight_topic"]["file"]] = meta["oversight_topic"]["name"]
    titles["Meeting"] = f"Meeting agenda, Legistar event {meta['legistar']['event_id']}"
    rows: dict[tuple[str, str], dict] = {}
    for line in pre_readme.read_text(encoding="utf-8").splitlines():
        m = README_ROW.match(line)
        if not m:
            continue
        matter, name, url, mod, fname = m.groups()
        rows[(matter, name)] = {"matter_file": matter, "attachment_name": name, "legistar_url": url,
                                "last_modified_utc": mod, "filename": fname, "_src": pre_dir / fname}
    for matter, name, mod, url, fname, nbytes in read_json(post_json):
        src = post_dir / fname
        if src.stat().st_size != nbytes:
            die(f"post-hearing {fname}: {src.stat().st_size} bytes on disk, manifest says {nbytes}")
        rows[(matter, name)] = {"matter_file": matter, "attachment_name": name, "legistar_url": url,
                                "last_modified_utc": mod, "filename": fname, "_src": src}
    # A filename shared by several matters (or re-saved post-hearing) resolves to the newest copy.
    newest: dict[str, Path] = {}
    for r in rows.values():
        if r["_src"].parent == post_dir or r["filename"] not in newest:
            newest[r["filename"]] = r["_src"]
    dest = out / "legistar"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for fname, src in sorted(newest.items()):
        if not src.is_file():
            die(f"legistar source missing: {src}")
        shutil.copy2(src, dest / fname)
    manifest = []
    for r in sorted(rows.values(), key=lambda r: (r["matter_file"] != meta["oversight_topic"]["file"],
                                                   r["matter_file"], r["attachment_name"])):
        if r["matter_file"] not in titles:
            die(f"no title for matter {r['matter_file']!r}")
        manifest.append({**{k: r[k] for k in ("matter_file", "attachment_name", "legistar_url",
                                                 "last_modified_utc", "filename")},
                         "matter_title": titles[r["matter_file"]],
                         "bytes": (dest / r["filename"]).stat().st_size})
    write_csv(dest / "manifest.csv", MANIFEST_FIELDS, manifest)
    return manifest


def read_manifest(out: Path) -> list[dict]:
    p = out / "legistar" / "manifest.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---- per-hearing READMEs -----------------------------------------------------------------
def hearing_readme(meta: dict, stats: dict, speakers: list[dict], manifest: list[dict]) -> str:
    conf = stats["confidence_counts"]
    bills = "\n".join(f"| {b['file']} | {b['name']} | {b['lead_sponsor']} |" for b in meta["bills"])
    cats = {}
    for s in speakers:
        cats[s["category"]] = cats.get(s["category"], 0) + 1
    cat_lines = "\n".join(f"| `{k}` | {CATEGORIES[k][0]} | {cats.get(k, 0)} |" for k in CATEGORIES)
    docs = len({m["filename"] for m in manifest})
    pending = "".join(f"- {n}\n" for n in (archive_note(meta), release_note(meta)) if n)
    return f"""# {meta['body']}: {meta['title']}

**{meta['date']}, {meta['start_time_local']}, {meta['location']}.** Legistar event
[{meta['legistar']['event_id']}]({meta['legistar']['url']}). Video length {meta['video']['duration_hms']}.

- Watch: [Internet Archive]({meta['video']['internet_archive_url']}){(' (' + archive_note(meta) + ')') if archive_note(meta) else ''}
- Council's own video: [councilnyc.viebit.com]({meta['video']['council_source_url']})

This is a machine transcript with speaker names added by BetaNYC. **It is not an official
record.** Check the video before quoting anyone.
{(chr(10) + meta['disclosure'] + chr(10)) if meta.get('disclosure') else ''}
## Files

| File | What it is |
|---|---|
| `hearing.json` | Machine-readable metadata: body, date, Legistar ids, video links, bills heard, counts |
| `transcript/transcript.txt` | Unedited transcript, one turn per paragraph: `[HH:MM:SS] Name: text` |
| `transcript/transcript-clean.txt` | Clean verbatim: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. |
| `transcript/turns.csv`, `turns.json` | One row per speaker turn: `{', '.join(TURN_FIELDS)}` |
| `transcript/words.json` | Every word with its start and end time in seconds and its `turn_id` (unedited words) |
| `transcript/captions.vtt` | WebVTT captions, speaker in a `<v>` tag, cues of 7 seconds or less |
| `speakers.csv` | One row per speaker: `{', '.join(SPEAKER_FIELDS)}` |
| `legistar/` | {docs} documents from Legistar plus `manifest.csv` with each document's Legistar URL and last-modified time |
| `media/` | 16 kbps Opus audio, and pointers to the video and the full-quality MP3 |

Times are seconds from the start of the Council's recording (00:00:00 is the first frame,
not 11:00 AM).

## Bills and topics heard

Oversight topic: {meta['oversight_topic']['file']}, {meta['oversight_topic']['name']}.

| File | Subject | Lead sponsor |
|---|---|---|
{bills}

## Counts

- Turns: {stats['turns']}; speakers (name and role pairs): {stats['speakers']}; words: {stats['words']}
- Speaker-name confidence by turn: high {conf['high']}, medium {conf['medium']}, low {conf['low']}
- Turns with no identified speaker (category `unidentified`): {stats['unidentified_turns']}

Speaker categories (derived from the role, see the repository README for the rule):

| Category | Meaning | Speakers |
|---|---|---|
{cat_lines}

## Known gaps

- Speaker names were assigned after transcription. A low-confidence name shows `[?]` in the
  transcripts and `low` in `turns.csv`. Some turns contain two voices (for example a question
  and the start of an answer) because the diarization did not split them.
- {stats['unidentified_turns']} turns are labeled Unidentified: short interjections, audience
  remarks, off-mic presiding remarks, and a few witnesses whose names were not audible.
- Speaker names come from self-introductions, the chair calling on people, the on-screen name
  banner (shown only for the Speaker), and voice clusters. Names were assigned by AI agents working from these sources, at BetaNYC's direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person.
- Witness names are spelled as the transcription heard them and have not been checked against a witness list or written testimony. Some are likely misspelled; corrections are welcome as GitHub issues.
- The clean verbatim copy edit was AI-assisted: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build checks that every turn's
  timestamp and speaker label match the unedited transcript, which is kept alongside in every
  export.
- Talk time is approximate: a few turns contain two voices.
{pending}"""


def media_readme(meta: dict) -> str:
    mp3 = meta["media"]["audio_mp3"]
    opus = meta["media"]["audio_opus"]
    return f"""# Media: {meta['title']} ({meta['date']})

The video and audio are a public record produced by the New York City Council. BetaNYC's
license does not cover them.

| What | Where |
|---|---|
| Video (Internet Archive copy) | {meta['video']['internet_archive_url']} {archive_note(meta)} |
| Video (Council source) | {meta['video']['council_source_url']} |
| Audio, small | `{Path(opus['path']).name}` in this folder. {opus['format']} |
| Audio, full quality | GitHub Release `{mp3['release_tag']}`, asset `{mp3['asset_name']}` ({human_bytes(mp3['bytes'])}, {mp3['format']}): {mp3['release_url']} {release_note(meta)} |

The MP3 is the file that was transcribed. It is kept out of git because GitHub refuses files
over 100 MB. The Opus file was encoded from the same audio and plays the same timeline, so
transcript timestamps line up with both.
"""


# ---- index.html -----------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def chart_svg(speakers: list[dict], slug: str, top: int = 25) -> str:
    rows = speakers[:top]
    label_w, bar_w, value_w, row_h, top_pad = 400, 300, 80, 26, 8
    width = label_w + bar_w + value_w
    height = top_pad * 2 + row_h * len(rows)
    mx = max(r["talk_seconds"] for r in rows) or 1
    desc = "; ".join(f"{r['speaker_name']} ({CATEGORIES[r['category']][0]}): {human_dur(r['talk_seconds'])}"
                     for r in rows)
    parts = [(f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img" '
              f'aria-labelledby="chart-title-{slug} chart-desc-{slug}" xmlns="http://www.w3.org/2000/svg">'),
             f'<title id="chart-title-{slug}">Top {len(rows)} speakers by talk time</title>',
             f'<desc id="chart-desc-{slug}">Horizontal bar chart, longest first. {esc(desc)}.</desc>']
    for n, r in enumerate(rows):
        y = top_pad + n * row_h
        w = max(2, bar_w * r["talk_seconds"] / mx)
        color = CATEGORIES[r["category"]][1]
        role = r["speaker_role"].replace(WITNESS_PREFIX, "")
        label = r["speaker_name"] if len(r["speaker_name"]) <= 34 else r["speaker_name"][:33] + "…"
        parts.append(
            f'<g><title>{esc(r["speaker_name"])}, {esc(r["speaker_role"])}: {human_dur(r["talk_seconds"])} '
            f'in {r["turns"]} turns</title>'
            f'<text x="{label_w - 8}" y="{y + 17}" text-anchor="end" class="lbl">{esc(label)}'
            f'<tspan class="role"> · {esc(role if len(role) <= 30 else role[:29] + "…")}</tspan></text>'
            f'<rect x="{label_w}" y="{y + 4}" width="{w:.1f}" height="{row_h - 8}" fill="{color}"/>'
            f'<text x="{label_w + w + 6:.1f}" y="{y + 17}" class="val">{human_dur(r["talk_seconds"])}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def file_row(base: Path, rel: str, label: str, fmt: str) -> str:
    size = human_bytes((base / rel).stat().st_size)
    return f'<li><a href="{esc(rel)}" download>{esc(label)}</a> <span class="meta">{esc(fmt)}, {size}</span></li>'


def hearing_card(slug: str) -> str:
    hdir = REPO / "hearings" / slug
    meta = read_json(hdir / "hearing.json")
    with open(hdir / "speakers.csv", encoding="utf-8", newline="") as f:
        speakers = [{**r, "talk_seconds": float(r["talk_seconds"]), "turns": int(r["turns"])}
                    for r in csv.DictReader(f)]
    speakers.sort(key=lambda r: -r["talk_seconds"])
    manifest = read_manifest(hdir)
    p = f"hearings/{slug}/"
    files = [
        ("transcript/transcript-clean.txt", "Transcript, clean verbatim", "Plain text"),
        ("transcript/transcript.txt", "Transcript, unedited", "Plain text"),
        ("transcript/turns.csv", "Speaker turns", "CSV"),
        ("transcript/turns.json", "Speaker turns", "JSON"),
        ("transcript/words.json", "Word-level timings", "JSON"),
        ("transcript/captions.vtt", "Captions", "WebVTT"),
        ("speakers.csv", "Speakers and talk time", "CSV"),
        ("hearing.json", "Hearing metadata", "JSON"),
        ("legistar/manifest.csv", "Legistar document list", "CSV"),
        (meta["media"]["audio_opus"]["path"], "Audio, small", meta["media"]["audio_opus"]["format"]),
    ]
    file_items = "\n".join(file_row(REPO, p + rel, label, fmt) for rel, label, fmt in files)
    mp3 = meta["media"]["audio_mp3"]
    file_items += (f'\n<li><a href="{esc(mp3["release_url"])}">Audio, full quality (GitHub Release)</a> '
                   f'<span class="meta">{esc(mp3["format"])}, {human_bytes(mp3["bytes"])}{(". " + esc(release_note(meta))) if release_note(meta) else ""}</span></li>')
    seen, doc_items = set(), []
    for m in manifest:
        if m["filename"] in seen:
            continue
        seen.add(m["filename"])
        ext = Path(m["filename"]).suffix.lstrip(".").upper()
        doc_items.append(f'<li><a href="{esc(p + "legistar/" + m["filename"])}" download>'
                         f'{esc(m["matter_file"])}: {esc(m["attachment_name"])}</a> '
                         f'<span class="meta">{ext}, {human_bytes(int(m["bytes"]))}</span></li>')
    legend = "".join(f'<li><span class="sw" style="background:{c}" aria-hidden="true"></span>{esc(n)}</li>'
                     for k, (n, c) in CATEGORIES.items() if any(s["category"] == k for s in speakers[:25]))
    table = "".join(f"<tr><td>{esc(s['speaker_name'])}</td><td>{esc(s['speaker_role'])}</td>"
                    f"<td>{esc(CATEGORIES[s['category']][0])}</td><td>{s['turns']}</td>"
                    f"<td>{human_dur(s['talk_seconds'])}</td></tr>" for s in speakers[:25])
    bills = "".join(f"<li>{esc(b['file'])}: {esc(b['name'])} <span class=\"meta\">(lead sponsor "
                    f"{esc(b['lead_sponsor'])})</span></li>" for b in meta["bills"])
    st = meta["stats"]
    return f"""
<article class="card" aria-labelledby="h-{slug}">
  <h3 id="h-{slug}">{esc(meta['body'])}: {esc(meta['title'])}</h3>
  <p class="facts"><strong>{esc(meta['date'])}</strong>, {esc(meta['start_time_local'])} at {esc(meta['location'])}.
    Duration {esc(meta['video']['duration_hms'])}. {st['turns']} speaker turns, {st['speakers']} speakers.</p>
  <p class="actions">
    <a class="button" href="{esc(meta['video']['internet_archive_url'])}">Watch on the Internet Archive</a>
    <a href="{esc(meta['video']['council_source_url'])}">Council video source</a> ·
    <a href="{esc(meta['legistar']['url'])}">Legistar event {meta['legistar']['event_id']}</a> ·
    <a href="{esc(p + 'README.md')}">Hearing README</a>
  </p>
  {('<p class="meta">' + esc(archive_note(meta)) + '</p>') if archive_note(meta) else ''}
  {('<p>' + esc(meta['disclosure']) + '</p>') if meta.get('disclosure') else ''}
  <h4>Downloads</h4>
  <ul class="files">
{file_items}
  </ul>
  <details>
    <summary>Legistar documents ({len(doc_items)} files)</summary>
    <ul class="files">{''.join(doc_items)}</ul>
  </details>
  <details>
    <summary>Bills heard ({len(meta['bills'])}) and oversight topic</summary>
    <p>Oversight topic {esc(meta['oversight_topic']['file'])}: {esc(meta['oversight_topic']['name'])}.</p>
    <ul>{bills}</ul>
  </details>
  <h4>Who spoke the longest</h4>
  <p>Top 25 speakers by total talk time. Colors show the speaker category; the role is also written next to each name.</p>
  <ul class="legend" aria-label="Chart legend">{legend}</ul>
  {chart_svg(speakers, slug)}
  <p class="meta">Talk time is approximate: a few turns contain two voices.</p>
  <details>
    <summary>Chart data as a table</summary>
    <table><caption>Top 25 speakers by talk time</caption>
      <thead><tr><th scope="col">Speaker</th><th scope="col">Role</th><th scope="col">Category</th><th scope="col">Turns</th><th scope="col">Talk time</th></tr></thead>
      <tbody>{table}</tbody></table>
  </details>
</article>"""


def build_index() -> None:
    slugs = sorted((p.parent.name for p in (REPO / "hearings").glob("*/hearing.json")), reverse=True)
    cards = "\n".join(hearing_card(s) for s in slugs)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NYC Council hearing transcripts · BetaNYC</title>
<meta name="description" content="Open transcripts, speaker data and documents for NYC Council hearings, from BetaNYC.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;700&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
<style>
:root {{ --blue:#2359a8; --text:#414141; --border:#949494; --bg-blue:#EEF4FF; --bg-light:#F9FAFF; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Poppins, sans-serif; font-size:17px; line-height:30px; color:var(--text); background:#fff; }}
.wrap {{ max-width:1230px; margin:0 auto; padding:0 max(1.25rem, 5vw); }}
header.site {{ border-bottom:1px solid var(--border); padding:16px 0; }}
header.site img {{ height:48px; width:auto; display:block; }}
h1 {{ font-family:Poppins, sans-serif; font-weight:700; font-size:clamp(32px, 5vw, 51px); line-height:1.4; color:#000; margin:36px 0 16px; }}
h2, h3, h4 {{ font-family:Roboto, sans-serif; font-weight:700; color:#000; }}
h2 {{ font-size:32px; line-height:46px; margin:54px 0 16px; }}
h3 {{ font-size:22px; line-height:30px; margin:0 0 11px; }}
h4 {{ font-size:20px; line-height:30px; margin:24px 0 8px; }}
.lede {{ max-width:750px; }}
a {{ color:var(--blue); text-decoration:underline; }}
a:focus-visible, summary:focus-visible {{ outline:3px solid var(--blue); outline-offset:2px; }}
.card {{ border:1px solid var(--border); border-radius:0; padding:24px; margin:24px 0; background:#fff; }}
.button {{ display:inline-block; background:var(--blue); color:#fff; text-decoration:none; padding:8px 30px; line-height:29px; margin-right:11px; }}
.button:hover {{ background:#1b467f; }}
.button:focus-visible {{ outline:3px solid #000; }}
.meta {{ color:#595959; font-size:15px; }}
ul.files {{ list-style:none; padding:0; margin:0; columns:2 340px; }}
ul.files li {{ break-inside:avoid; padding:2px 0; }}
details {{ margin:11px 0; }}
summary {{ cursor:pointer; color:var(--blue); }}
.legend {{ list-style:none; padding:0; display:flex; flex-wrap:wrap; gap:4px 24px; }}
.legend .sw {{ display:inline-block; width:14px; height:14px; margin-right:7px; vertical-align:-1px; border:1px solid #414141; }}
svg.chart {{ max-width:860px; height:auto; display:block; margin:11px 0; }}
svg.chart text {{ font-family:Roboto, sans-serif; font-size:13px; fill:#414141; }}
svg.chart .role {{ fill:#595959; font-size:12px; }}
table {{ border-collapse:collapse; font-size:15px; line-height:22px; }}
th, td {{ border:1px solid var(--border); padding:4px 8px; text-align:left; }}
.note {{ background:var(--bg-blue); padding:16px 24px; max-width:750px; }}
footer {{ border-top:1px solid var(--border); margin-top:54px; padding:24px 0; font-size:15px; }}
</style>
</head>
<body>
<a href="#main" class="meta" style="position:absolute;left:-999px" onfocus="this.style.left='8px'" onblur="this.style.left='-999px'">Skip to content</a>
<header class="site"><div class="wrap"><a href="https://beta.nyc/"><img src="assets/betanyc-logo.svg" alt="BetaNYC home" width="142" height="48"></a></div></header>
<main id="main" class="wrap">
<h1>NYC Council hearing transcripts</h1>
<p class="lede">Searchable transcripts, speaker data, captions and the Council's own documents for New York City Council hearings, free to download and reuse. Each hearing has a plain-text transcript, a table of every speaker turn with timestamps, word-level timings, captions, a speaker list, and the Legistar documents that were before the Council. Use them to read, quote (after checking the video), search, or chart who said what.</p>
<p class="lede">Published by <a href="https://beta.nyc/">BetaNYC</a>. Source code and full history: <a href="https://github.com/BetaNYC/hearings-transcripts">github.com/BetaNYC/hearings-transcripts</a>.</p>

<h2>Hearings</h2>
{cards}

<h2>How this was made</h2>
<ol class="lede">
<li>The Council's published video was converted to audio with ffmpeg.</li>
<li>The audio was transcribed by Deepgram's Nova-3 model with speaker diarization, which groups speech by voice but does not know names.</li>
<li>Names were assigned from self-introductions, the chair calling on people, the on-screen name banner (shown only for the Speaker), and voice clusters, and cross-checked against the Legistar roster, titles and bill sponsors and NYS Open Legislation member and sponsor records. Names were assigned by AI agents working from these sources, at BetaNYC&#x27;s direction. Elected officials were checked against Legistar and NYS Open Legislation. Other names were not individually verified by a person.</li>
<li>A clean verbatim copy was produced with AI assistance: fillers, stutters and false starts removed; punctuation, spelling and number formatting fixed; and words the transcription clearly misheard, including names, corrected. Speaker labels and timestamps are unchanged. The build script checks that every turn's timestamp and speaker label match the unedited copy.</li>
<li><code>scripts/build_hearing.py</code> produced every export and this page. See <a href="scripts/README.md">scripts/README.md</a>.</li>
</ol>

<h2>Known limits</h2>
<div class="note">
<p><strong>This is a machine transcript, not an official record of the Council.</strong> Words can be wrong, and a speaker name can be wrong.</p>
<ul>
<li><code>[?]</code> after a name marks a low-confidence speaker label. Some turns are labeled Unidentified.</li>
<li>Witness names are spelled as the transcription heard them and have not been checked against a witness list or written testimony. Some are likely misspelled; corrections are welcome as GitHub issues.</li>
<li>Talk time is approximate: a few turns contain two voices.</li>
<li>Check the video at the timestamp before quoting anyone.</li>
<li>Timestamps count from the start of the Council's recording, not the clock time of the hearing.</li>
</ul>
</div>

<h2>License and citation</h2>
<p class="lede">BetaNYC's work here (transcripts, speaker labels, exports, and this page's text) is licensed <a href="LICENSE-DATA">CC BY 4.0</a>. The code is <a href="LICENSE">MIT</a>. The video, audio and Legistar documents are public records produced by the New York City Council; our license does not cover them. To cite, see <a href="CITATION.cff">CITATION.cff</a>, or: BetaNYC (2026). <em>NYC Council hearing transcripts</em>. https://github.com/BetaNYC/hearings-transcripts</p>
</main>
<footer><div class="wrap">BetaNYC · <a href="https://beta.nyc/">beta.nyc</a> · <a href="README.md">About this repository</a></div></footer>
</body>
</html>
"""
    write_text(REPO / "index.html", page)
    log("index_written", hearings=len(slugs))


# ---- main -----------------------------------------------------------------------------------
def build_hearing(a: argparse.Namespace) -> None:
    for p in (a.meta, a.deepgram, a.labels, a.transcript, a.transcript_clean):
        if not p or not Path(p).is_file():
            die(f"required input missing: {p}")
    meta = read_json(Path(a.meta))
    out = REPO / "hearings" / meta["slug"]
    dg = read_json(Path(a.deepgram))
    labels = read_json(Path(a.labels))
    turns = build_turns(dg, labels, Path(a.transcript), Path(a.transcript_clean))
    words = build_words(turns)
    cues = build_cues(turns)
    speakers = build_speakers(turns)
    log("parsed", turns=len(turns), words=len(words), cues=len(cues), speakers=len(speakers))

    tdir = out / "transcript"
    tdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.transcript, tdir / "transcript.txt")
    shutil.copyfile(a.transcript_clean, tdir / "transcript-clean.txt")
    pub = [public_turn(t) for t in turns]
    write_csv(tdir / "turns.csv", TURN_FIELDS, pub)
    write_text(tdir / "turns.json", json.dumps(pub, ensure_ascii=False, indent=1) + "\n")
    write_text(tdir / "words.json", json.dumps(words, ensure_ascii=False, separators=(",", ":")) + "\n")
    write_text(tdir / "captions.vtt", render_vtt(cues, meta))
    write_csv(out / "speakers.csv", SPEAKER_FIELDS, speakers)

    if a.audio_opus:
        src = Path(a.audio_opus)
        if src.stat().st_size >= MAX_FILE_BYTES:
            die(f"{src} is {src.stat().st_size} bytes; GitHub refuses files over 100 MB")
        dst = out / meta["media"]["audio_opus"]["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst)
    write_text(out / "media" / "README.md", media_readme(meta))

    leg = (a.legistar_pre_readme, a.legistar_pre_dir, a.legistar_post_json, a.legistar_post_dir)
    if any(leg):
        if not all(leg):
            die("give all four --legistar-* options, or none")
        manifest = build_legistar(meta, out, *(Path(x) for x in leg))
    else:
        manifest = read_manifest(out)

    conf = {c: sum(t["confidence"] == c for t in turns) for c in VALID_CONFIDENCE}
    stats = {"turns": len(turns), "speakers": len(speakers), "words": len(words),
             "duration_sec": dg.get("duration_sec"), "confidence_counts": conf,
             "unidentified_turns": sum(categorize(t["speaker_name"], t["speaker_role"]) == "unidentified"
                                       for t in turns),
             "legistar_documents": len({m["filename"] for m in manifest})}
    hearing = {**meta, "stats": stats,
               "license": {"data": "CC-BY-4.0 (BetaNYC's transcripts, labels and exports)",
                           "public_records": "Video, audio and Legistar documents are public records "
                                             "produced by the New York City Council."}}
    write_text(out / "hearing.json", json.dumps(hearing, ensure_ascii=False, indent=2) + "\n")
    write_text(out / "README.md", hearing_readme(meta, stats, speakers, manifest))

    for f in out.rglob("*"):
        if f.is_file() and f.stat().st_size >= MAX_FILE_BYTES:
            die(f"{f} is over 100 MB")
    log("hearing_written", slug=meta["slug"], out=out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index-only", action="store_true", help="only rebuild index.html")
    ap.add_argument("--meta")
    ap.add_argument("--deepgram")
    ap.add_argument("--labels")
    ap.add_argument("--transcript")
    ap.add_argument("--transcript-clean")
    ap.add_argument("--audio-opus")
    ap.add_argument("--legistar-pre-readme")
    ap.add_argument("--legistar-pre-dir")
    ap.add_argument("--legistar-post-json")
    ap.add_argument("--legistar-post-dir")
    a = ap.parse_args(argv)
    if not a.index_only:
        build_hearing(a)
    build_index()


if __name__ == "__main__":
    main()
