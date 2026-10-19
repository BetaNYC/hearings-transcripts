#!/usr/bin/env python3
"""Download a NYC Council hearing video and captions from Viebit, then make the two audio files.

Python 3.11 to 3.14, standard library only. Needs ffmpeg and ffprobe on PATH.

    python3 scripts/fetch_media.py --event-json <legistar-dir>/event.json --out <media-dir>
    python3 scripts/fetch_media.py --viebit-url 'https://councilnyc.viebit.com/vod/?s=true&v=NYCC-PV-CH-CHA_261016-101016.mp4' --out <media-dir>

Where the URLs come from (observed, not documented by Viebit; re-check if a step fails):

1. Legistar's event record carries `EventVideoPath`, the Council's Viebit page
   (`https://councilnyc.viebit.com/vod/?s=true&v=<file>.mp4`). `fetch_legistar.py` saves it.
2. That page embeds `var pageConfig = {...};`, a JSON object with `video.id` (the Viebit hash),
   `video.title` (the original file name), `video.src` (an HLS playlist) and `video.textTracks`
   (the Council's WebVTT captions on `vbfast-vod.viebit.com`).
3. The MP4 sits beside the captions: `https://vbfast-vod.viebit.com/counciln/<id>/<title>`. This is
   the URL used for the 2026-10-05 hearing. On 2026-10-19 the watch page's Download button
   (`/vb/a/vod/vod-download?hash=<id>`, from the page's own script) redirected a browser to the
   same file under a `/dr/` path with the same size; that endpoint returns 400 outside a browser,
   so this script does not use it. Before downloading, the script checks with a one-byte range
   request that the URL answers 206 with a video/mp4 body, and stops if not. `--mp4-url` overrides.

Downloads are data: they are written to --out and never executed. Re-running is safe: a complete
MP4 or VTT is not fetched again, a partial MP4 (`.part`) is resumed, and audio files are rebuilt
only when missing, older than the video, after the video was fetched again, or with --force-audio.
ffmpeg writes to `<name>.partial.<ext>` and the file is renamed only when ffmpeg succeeds. Writes `media.json` with URLs, commands, sizes,
durations and sha256 for every file.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = "fetch_media"
ALLOWED_HOSTS = {"councilnyc.viebit.com", "vbfast-vod.viebit.com"}
USER_AGENT = "BetaNYC hearings-transcripts fetch_media.py (+https://github.com/BetaNYC/hearings-transcripts)"
FILENAME_RE = re.compile(r"^NYCC-[A-Z0-9-]+_\d{6}-\d{6}\.mp4$")
CHUNK = 8 * 1024 * 1024

MP3_NAME = "hearing-audio-64k.mp3"
OPUS_NAME = "hearing-audio-16k.opus"


def log(event: str, **fields) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"{ts} {SCRIPT} {event} {extra}".rstrip(), file=sys.stderr, flush=True)


def check_host(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        sys.exit(f"ERROR: {url} is not on an allowed Council video host ({', '.join(sorted(ALLOWED_HOSTS))})")
    return url


def parse_page_config(html: str) -> dict:
    """Return the `pageConfig` object embedded in a Viebit vod/watch page."""
    m = re.search(r"var\s+pageConfig\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("no `var pageConfig = {...};` in the Viebit page")
    return json.loads(m.group(1))


def media_urls(cfg: dict) -> dict:
    """From a pageConfig, the original file name, Viebit id, captions URL and MP4 URL."""
    video = cfg.get("video") or {}
    vid, title = video.get("id"), video.get("title")
    if not vid or not title:
        raise ValueError("pageConfig.video has no id or title")
    if not FILENAME_RE.match(title):
        raise ValueError(f"unexpected video title {title!r}; expected NYCC-..._YYMMDD-HHMMSS.mp4")
    captions = [t["src"] for t in video.get("textTracks") or [] if t.get("kind") == "captions" and t.get("src")]
    vtt = captions[0] if captions else None
    if vtt:
        base = vtt.rsplit("/", 1)[0]
        if not base.endswith(f"/{vid}"):
            raise ValueError(f"captions URL {vtt} is not in the folder for video id {vid}")
        mp4 = f"{base}/{title}"
    else:
        mp4 = None
    return {"viebit_id": vid, "filename": title, "vtt_url": vtt, "mp4_url": mp4,
            "hls_url": next((urllib.parse.urljoin(s["storage"], s["url"]) for s in video.get("src") or []
                             if s.get("storage") and s.get("url")), None),
            "date_created_unix": video.get("dateCreated")}


def http(url: str, *, headers: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(check_host(url), headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def probe_total_size(url: str) -> int:
    """One-byte range GET; return the full size from Content-Range, or stop."""
    with http(url, headers={"Range": "bytes=0-0"}) as r:
        ctype = r.headers.get("Content-Type", "")
        crange = r.headers.get("Content-Range", "")
        if r.status != 206 or not ctype.startswith("video/mp4"):
            sys.exit(f"ERROR: {url} answered {r.status} {ctype!r}; expected 206 video/mp4. Pass --mp4-url.")
    m = re.match(r"bytes 0-0/(\d+)$", crange)
    if not m:
        sys.exit(f"ERROR: no total size in Content-Range {crange!r} from {url}")
    return int(m.group(1))


def download(url: str, dest: Path, total: int | None = None, retries: int = 10) -> bool:
    """Stream url to dest via dest.part, resuming with Range. Skips a complete file.
    Returns True when it wrote a new file, False when the existing one was kept."""
    if dest.exists() and (total is None or dest.stat().st_size == total):
        log("skip_existing", file=dest.name, bytes=dest.stat().st_size)
        return False
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with http(url, headers=headers, timeout=120) as r:
                if have and r.status != 206:
                    have = 0  # server ignored Range; start over
                mode = "ab" if have else "wb"
                with open(part, mode) as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk)
            got = part.stat().st_size
            if total is None or got == total:
                part.replace(dest)
                log("downloaded", file=dest.name, bytes=got)
                return True
            log("short_read", file=dest.name, have=got, want=total)
        except OSError as e:
            log("retry", file=dest.name, attempt=attempt, error=type(e).__name__)
        time.sleep(5)
    sys.exit(f"ERROR: could not download {url} after {retries} attempts")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def partial_path(dest: Path) -> Path:
    """Where ffmpeg writes before the rename: same folder, same extension (ffmpeg picks the
    format from it), so a killed run never leaves a truncated file under the final name."""
    return dest.with_name(f"{dest.stem}.partial{dest.suffix}")


def audio_is_stale(dest: Path, video: Path, video_refetched: bool = False) -> bool:
    """Rebuild when the audio is missing, older than the video, or the video was just fetched again."""
    return video_refetched or not dest.exists() or dest.stat().st_mtime < video.stat().st_mtime


def make_audio(cmd: list[str], dest: Path) -> None:
    """Run one ffmpeg command (its last argument is dest) into a partial file, then rename."""
    tmp = partial_path(dest)
    subprocess.run(cmd[:-1] + [str(tmp)], check=True)
    if not tmp.is_file() or tmp.stat().st_size == 0:
        sys.exit(f"ERROR: ffmpeg wrote nothing for {dest.name}")
    tmp.replace(dest)


def audio_commands(video: Path, out: Path) -> list[tuple[Path, list[str]]]:
    """The two ffmpeg invocations, as argument lists (matching the 2026-10-05 files)."""
    return [
        (out / MP3_NAME, ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                          "-c:a", "libmp3lame", "-b:a", "64k", str(out / MP3_NAME)]),
        (out / OPUS_NAME, ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
                           "-c:a", "libopus", "-b:a", "16k", str(out / OPUS_NAME)]),
    ]


def file_record(path: Path, **extra) -> dict:
    rec = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path), **extra}
    if path.suffix in (".mp4", ".mp3", ".opus"):
        d = ffprobe_duration(path)
        rec |= {"duration_sec": round(d, 3), "duration_hms": hms(d)}
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--event-json", type=Path, help="event.json written by fetch_legistar.py")
    src.add_argument("--viebit-url", help="Council Viebit page URL (Legistar EventVideoPath)")
    ap.add_argument("--out", type=Path, required=True, help="media folder (outside the repo)")
    ap.add_argument("--mp4-url", help="override the MP4 URL derived from the page")
    ap.add_argument("--skip-audio", action="store_true")
    ap.add_argument("--force-audio", action="store_true", help="rebuild MP3 and Opus even if present")
    a = ap.parse_args(argv)

    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            sys.exit(f"ERROR: {binary} not found on PATH (brew install ffmpeg)")

    if a.event_json:
        ev = json.loads(a.event_json.read_text(encoding="utf-8"))
        page_url = (ev.get("event") or ev).get("EventVideoPath")
        if not page_url:
            sys.exit(f"ERROR: {a.event_json} has no EventVideoPath; the Council has not linked a video yet")
    else:
        page_url = a.viebit_url
    log("page", url=page_url)
    with http(page_url) as r:
        body = r.read()
        # Viebit gzips this page even when the request does not offer gzip (seen 2026-10-19).
        if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        html = body.decode("utf-8", "replace")
    cfg = parse_page_config(html)
    if not cfg.get("hasAccess", True):
        sys.exit("ERROR: Viebit says the video is not public")
    urls = media_urls(cfg)
    mp4_url = a.mp4_url or urls["mp4_url"]
    if not mp4_url:
        sys.exit("ERROR: no captions track to locate the MP4 beside; pass --mp4-url")

    a.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = probe_total_size(mp4_url)
    log("mp4", url=mp4_url, bytes=total)
    video = a.out / urls["filename"]
    video_refetched = download(mp4_url, video, total)

    vtt = None
    if urls["vtt_url"]:
        vtt = a.out / Path(urllib.parse.urlparse(urls["vtt_url"]).path).name
        download(urls["vtt_url"], vtt)

    commands = []
    if not a.skip_audio:
        for dest, cmd in audio_commands(video, a.out):
            commands.append(" ".join(cmd))
            if not a.force_audio and not audio_is_stale(dest, video, video_refetched):
                log("skip_existing", file=dest.name)
                continue
            log("ffmpeg", file=dest.name)
            make_audio(cmd, dest)

    files = [file_record(video, url=mp4_url)]
    if vtt:
        files.append(file_record(vtt, url=urls["vtt_url"]))
    for name in (MP3_NAME, OPUS_NAME):
        if (a.out / name).exists():
            files.append(file_record(a.out / name))
    record = {"generated_utc": started, "viebit_page": page_url, **urls, "mp4_url": mp4_url,
              "ffmpeg_version": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0],
              "audio_commands": commands, "files": files}
    (a.out / "media.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for f in files:
        log("file", **{k: f[k] for k in ("file", "bytes", "sha256") if k in f}, duration=f.get("duration_hms", "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
