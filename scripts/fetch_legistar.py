#!/usr/bin/env python3
"""Download a NYC Council hearing's Legistar record and every attachment.

Python 3.11 to 3.14, standard library only.

    LEGISTAR_TOKEN=... python3 scripts/fetch_legistar.py 22795 --out <dir> [--out <copy-dir>]

Built against the Legistar Web API reference (Granicus), https://webapi.legistar.com/Help :

- GET v1/{Client}/Events/{EventId}?EventItems=1&AgendaNote=1&MinutesNote=1&EventItemAttachments=1
  https://webapi.legistar.com/Help/Api/GET-v1-Client-Events-EventId_EventItems_AgendaNote_MinutesNote_EventItemAttachments
- GET v1/{Client}/Matters/{MatterId}
  https://webapi.legistar.com/Help/Api/GET-v1-Client-Matters-MatterId
- GET v1/{Client}/Matters/{MatterId}/Attachments
  https://webapi.legistar.com/Help/Api/GET-v1-Client-Matters-MatterId-Attachments

The client code is `nyc`. NYC requires a token, passed as the `token` URL parameter
("Some clients require use of API tokens ... provided as a URL parameter", https://webapi.legistar.com/Home/Examples).
It is read from the LEGISTAR_TOKEN environment variable and never written to disk or logs.

Writes to the first --out folder, then copies to every other --out:

- `event.json`: the API responses (event with items, each matter, each matter's attachments),
  plus the time they were fetched;
- `README.md`: a short description of the event and an attachment table;
- `manifest.csv`: `matter_file,matter_title,attachment_name,legistar_url,last_modified_utc,filename,bytes`,
  one row per downloaded file, the meeting agenda (and minutes, once published) first;
- the attachments, named `<matter-file>-<attachment-name>.<ext>`, lowercased with runs of other
  characters turned into `-` (the rule used for the 2026-10-05 post-hearing download).

Only files on Legistar's own hosts are downloaded. An attachment that is a hyperlink to some
other site is listed in the README, not fetched. Re-running is safe: every file is rewritten.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = "fetch_legistar"
API = "https://webapi.legistar.com/v1/nyc"
FILE_HOSTS = {"nyc.legistar1.com", "legistar.council.nyc.gov", "nyc.legistar.com"}
USER_AGENT = "BetaNYC hearings-transcripts fetch_legistar.py (+https://github.com/BetaNYC/hearings-transcripts)"
MANIFEST_COLUMNS = ["matter_file", "matter_title", "attachment_name", "legistar_url",
                    "last_modified_utc", "filename", "bytes"]


def log(event: str, **fields) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"{ts} {SCRIPT} {event} {extra}".rstrip(), file=sys.stderr, flush=True)


# ---- pure helpers (tested) -------------------------------------------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def attachment_filename(matter_file: str, attachment_name: str, url: str) -> str:
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".") or "bin"
    return f"{slugify(matter_file + ' ' + attachment_name)}.{ext}"


def short_utc(value: str | None) -> str:
    """'2026-10-15T15:39:11.387' -> '2026-10-15 15:39' (the manifest's format)."""
    return value[:16].replace("T", " ") if value else ""


def is_legistar_file(url: str | None) -> bool:
    return bool(url) and urllib.parse.urlparse(url).scheme == "https" and \
        (urllib.parse.urlparse(url).hostname or "") in FILE_HOSTS


def plan_files(event: dict, matters: dict[int, dict], attachments: dict[int, list[dict]]) -> tuple[list[dict], list[dict]]:
    """Return (downloads, skipped). Each download is a manifest row plus `url`.

    Order: meeting agenda, meeting minutes, then matters in agenda order and their
    attachments in Legistar's sort order. Duplicate filenames get -2, -3, ...
    """
    rows, skipped, used = [], [], set()

    def unique(name: str) -> str:
        stem, dot, ext = name.rpartition(".")
        n, cand = 1, name
        while cand in used:
            n += 1
            cand = f"{stem}-{n}{dot}{ext}"
        used.add(cand)
        return cand

    eid = event["EventId"]
    for key, label, fname, stamp in (("EventAgendaFile", "Agenda", "meeting-agenda.pdf", "EventAgendaLastPublishedUTC"),
                                     ("EventMinutesFile", "Minutes", "meeting-minutes.pdf", "EventMinutesLastPublishedUTC")):
        url = event.get(key)
        if url:
            rows.append({"matter_file": "Meeting", "matter_title": f"Meeting {label.lower()}, Legistar event {eid}",
                         "attachment_name": label, "legistar_url": url, "last_modified_utc": short_utc(event.get(stamp)),
                         "filename": unique(fname), "bytes": None})
    items = sorted(event.get("EventItems") or [], key=lambda i: (i.get("EventItemAgendaSequence") or 0))
    seen_matters = []
    for it in items:
        mid = it.get("EventItemMatterId")
        if mid and mid not in seen_matters:
            seen_matters.append(mid)
    for mid in seen_matters:
        m = matters[mid]
        for a in sorted(attachments.get(mid) or [], key=lambda a: (a.get("MatterAttachmentSort") or 0, a["MatterAttachmentId"])):
            url = a.get("MatterAttachmentHyperlink")
            base = {"matter_file": m["MatterFile"], "matter_title": m.get("MatterName") or m.get("MatterTitle") or "",
                    "attachment_name": a["MatterAttachmentName"], "legistar_url": url or "",
                    "last_modified_utc": short_utc(a.get("MatterAttachmentLastModifiedUtc"))}
            if not is_legistar_file(url):
                skipped.append(base)
                continue
            rows.append({**base, "filename": unique(attachment_filename(m["MatterFile"], a["MatterAttachmentName"], url)),
                         "bytes": None})
    return rows, skipped


def manifest_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def readme_text(event: dict, matters: dict[int, dict], rows: list[dict], skipped: list[dict], fetched_utc: str) -> str:
    date = (event.get("EventDate") or "")[:10]
    lines = [
        f"# Legistar: {event.get('EventBodyName')}, {date}",
        "",
        f"Downloaded {fetched_utc} by `scripts/fetch_legistar.py` from the Legistar Web API (client `nyc`).",
        "Council material, not BetaNYC's; reproduced for convenience.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Legistar event | {event['EventId']} |",
        f"| Body | {event.get('EventBodyName') or ''} |",
        f"| Date and time | {date} {event.get('EventTime') or ''} |",
        f"| Location | {event.get('EventLocation') or ''} |",
        f"| Agenda status | {event.get('EventAgendaStatusName') or ''} (last published {short_utc(event.get('EventAgendaLastPublishedUTC')) or 'n/a'} UTC) |",
        f"| Minutes status | {event.get('EventMinutesStatusName') or ''} |",
        f"| Video | {event.get('EventVideoPath') or 'none linked yet'} |",
        f"| Meeting page | {event.get('EventInSiteURL') or ''} |",
        "",
        "## Agenda items",
        "",
        "| # | File | Type | Title | Status |",
        "|---|---|---|---|---|",
    ]
    for it in sorted(event.get("EventItems") or [], key=lambda i: (i.get("EventItemAgendaSequence") or 0)):
        title = (it.get("EventItemMatterName") or it.get("EventItemTitle") or "").replace("|", "\\|")
        lines.append(f"| {it.get('EventItemAgendaSequence') or ''} | {it.get('EventItemMatterFile') or ''} | "
                     f"{it.get('EventItemMatterType') or ''} | {title} | {it.get('EventItemMatterStatus') or ''} |")
    # Row shape is the one build_hearing.py's README_ROW parses for --legistar-pre-readme.
    lines += ["", "## Files", "", "| Matter | Attachment | Last modified (UTC) | File | Bytes |", "|---|---|---|---|---|"]
    for r in rows:
        name = r["attachment_name"].replace("|", "\\|").replace("]", ")").replace("[", "(")
        lines.append(f"| {r['matter_file']} | [{name}]({r['legistar_url']}) | {r['last_modified_utc']} | "
                     f"`{r['filename']}` | {r['bytes']} |")
    if skipped:
        lines += ["", "Not downloaded (not a file on Legistar):", ""]
        lines += [f"- {s['matter_file']}: {s['attachment_name']} {s['legistar_url']}" for s in skipped]
    lines += ["", "`manifest.csv` lists the same files with their source URLs. `event.json` holds the API responses.", ""]
    return "\n".join(lines)


# ---- network ---------------------------------------------------------------------------
def api_get(path: str, token: str, params: dict | None = None):
    q = urllib.parse.urlencode({**(params or {}), "token": token})
    req = urllib.request.Request(f"{API}{path}?{q}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    log("api_get", path=path, params=",".join(f"{k}={v}" for k, v in (params or {}).items()) or "-")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit(f"ERROR: Legistar answered {e.code} for {path}; check LEGISTAR_TOKEN")
            if e.code < 500 or attempt == 3:
                sys.exit(f"ERROR: Legistar answered {e.code} for {path}")
        except OSError as e:
            if attempt == 3:
                sys.exit(f"ERROR: Legistar request failed for {path}: {type(e).__name__}")
        time.sleep(3 * attempt)


def download(url: str, dest: Path) -> int:
    if not is_legistar_file(url):
        raise ValueError(f"refusing non-Legistar URL {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        final = r.geturl()
        if not is_legistar_file(final):  # urllib follows redirects; re-check where we ended up
            raise ValueError(f"{url} redirected to non-Legistar URL {final}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    return dest.stat().st_size


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("event_id", type=int)
    ap.add_argument("--out", type=Path, action="append", required=True,
                    help="output folder; repeat to write copies")
    ap.add_argument("--offline", action="store_true",
                    help="no network: rewrite README.md and manifest.csv from the event.json and "
                         "files already in the first --out (after a format change)")
    a = ap.parse_args(argv)

    if a.offline:
        out = a.out[0]
        raw = json.loads((out / "event.json").read_text(encoding="utf-8"))
        matters = {m["MatterId"]: m for m in raw["matters"]}
        attachments = {int(k): v for k, v in raw["matter_attachments"].items()}
        rows, skipped = plan_files(raw["event"], matters, attachments)
        for r in rows:
            r["bytes"] = (out / r["filename"]).stat().st_size
        (out / "manifest.csv").write_text(manifest_csv(rows), encoding="utf-8")
        (out / "README.md").write_text(readme_text(raw["event"], matters, rows, skipped, raw["fetched_utc"]),
                                       encoding="utf-8")
        for copy in a.out[1:]:
            for n in ("manifest.csv", "README.md"):
                shutil.copy2(out / n, copy / n)
        log("offline_rewrite", files=len(rows))
        return 0

    token = os.environ.get("LEGISTAR_TOKEN", "").strip()
    if not token:
        sys.exit("ERROR: LEGISTAR_TOKEN is not set. NYC's Legistar Web API requires a token "
                 "(https://webapi.legistar.com/Home/Examples); ask the Council for one.")

    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = api_get(f"/events/{a.event_id}", token,
                    {"EventItems": 1, "AgendaNote": 1, "MinutesNote": 1, "EventItemAttachments": 1})
    matter_ids = []
    for it in event.get("EventItems") or []:
        if it.get("EventItemMatterId") and it["EventItemMatterId"] not in matter_ids:
            matter_ids.append(it["EventItemMatterId"])
    matters = {mid: api_get(f"/matters/{mid}", token) for mid in matter_ids}
    attachments = {mid: api_get(f"/matters/{mid}/attachments", token) for mid in matter_ids}

    rows, skipped = plan_files(event, matters, attachments)
    out = a.out[0]
    out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        r["bytes"] = download(r["legistar_url"], out / r["filename"])
        log("downloaded", file=r["filename"], bytes=r["bytes"])

    raw = {"fetched_utc": fetched, "api": API, "event": event,
           "matters": [matters[m] for m in matter_ids],
           "matter_attachments": {str(m): attachments[m] for m in matter_ids}}
    (out / "event.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "manifest.csv").write_text(manifest_csv(rows), encoding="utf-8")
    (out / "README.md").write_text(readme_text(event, matters, rows, skipped, fetched), encoding="utf-8")

    names = ["event.json", "manifest.csv", "README.md"] + [r["filename"] for r in rows]
    for copy in a.out[1:]:
        copy.mkdir(parents=True, exist_ok=True)
        for n in names:
            shutil.copy2(out / n, copy / n)
        log("copied", to=copy, files=len(names))
    log("done", event_id=a.event_id, files=len(rows), skipped=len(skipped),
        video=event.get("EventVideoPath") or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
