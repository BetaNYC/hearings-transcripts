"""Tests for build_hearing.py and the files it built. Standard library only.

Run from the repository root:  python3 -m unittest discover -s scripts -v
"""

from __future__ import annotations

import csv
import functools
import http.server
import json
import re
import sys
import threading
import unittest
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hearing as bh

REPO = Path(__file__).resolve().parent.parent
SLUG = "2026-10-05-committee-of-the-whole-ai"
H = REPO / "hearings" / SLUG
T = H / "transcript"
EXPECTED_TURNS = 830
EPS = 0.002


def load_turns():
    return json.loads((T / "turns.json").read_text(encoding="utf-8"))


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.imgs, self.headings = [], [], []
        self.lang = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        for key in ("href", "src"):
            if key in a:
                self.links.append(a[key])
        if tag == "img":
            self.imgs.append(a)
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))


def relative_links(html_text: str) -> list[str]:
    p = LinkParser()
    p.feed(html_text)
    out = []
    for link in p.links:
        u = urllib.parse.urlparse(link)
        if u.scheme or u.netloc or link.startswith(("#", "mailto:")):
            continue
        out.append(urllib.parse.unquote(u.path))
    return out


class UnitTests(unittest.TestCase):
    def test_merge_turns_gap_and_cluster(self):
        segs = [
            {"start": 0, "end": 2, "speaker": 1},
            {"start": 6.9, "end": 8, "speaker": 1},   # gap 4.9 s, same cluster -> merge
            {"start": 13, "end": 14, "speaker": 1},   # gap 5.0 s -> new turn
            {"start": 14.5, "end": 15, "speaker": 2},  # new cluster -> new turn
        ]
        turns = bh.merge_turns(segs)
        self.assertEqual([len(t["segments"]) for t in turns], [2, 1, 1])
        self.assertEqual(turns[0]["end"], 8)

    def test_display_name(self):
        self.assertEqual(bh.display_name("Julie Menin", "Speaker", "high"), "Speaker Julie Menin")
        self.assertEqual(bh.display_name("Gale Brewer", "Council Member", "low"), "CM Gale Brewer [?]")
        self.assertEqual(bh.display_name("Logan Graham", "Witness — Anthropic", "medium"), "Logan Graham (Anthropic)")
        self.assertEqual(bh.display_name("Alex Bores", "NY State Assembly Member, AD 73", "high"),
                         "Alex Bores (NY State Assembly Member, AD 73)")
        self.assertEqual(bh.display_name("Committee Counsel", "Committee Counsel", "low"), "Committee Counsel [?]")

    def test_categorize(self):
        c = bh.categorize
        self.assertEqual(c("Julie Menin", "Speaker"), "council")
        self.assertEqual(c("Committee Counsel", "Committee Counsel"), "council-staff")
        self.assertEqual(c("Morgan Dwyer", "Witness — OpenAI"), "ai-company")
        self.assertEqual(c("Sarah Milstein", "Witness — OTI"), "city-official")
        self.assertEqual(c("Kristen Gonzalez", "NY State Senator, SD 59"), "state-or-other-elected")
        self.assertEqual(c("Jumaane Williams", "NYC Public Advocate"), "state-or-other-elected")
        self.assertEqual(c("Noel Hidalgo", "Witness — BetaNYC"), "witness")
        self.assertEqual(c("Unidentified Witness", "Witness — company panel"), "unidentified")
        self.assertEqual(c("Unidentified", "Unidentified"), "unidentified")
        with self.assertRaises(ValueError):
            c("Someone", "Mayor")

    def test_pending_caveats_toggle(self):
        meta = {"video": {"archive_playable": False}, "media": {"audio_mp3": {"release_published": False}}}
        self.assertTrue(bh.archive_note(meta) and bh.release_note(meta))
        meta["video"]["archive_playable"] = True
        meta["media"]["audio_mp3"]["release_published"] = True
        self.assertEqual((bh.archive_note(meta), bh.release_note(meta)), ("", ""))

    def test_vtt_timestamp(self):
        self.assertEqual(bh.vtt_ts(36492.4806), "10:08:12.481")
        self.assertEqual(bh.hms(103.999), "00:01:43")


class BuiltFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.turns = load_turns()

    def test_turn_count(self):
        self.assertEqual(len(self.turns), EXPECTED_TURNS)
        self.assertEqual([t["turn_id"] for t in self.turns], list(range(EXPECTED_TURNS)))

    def test_turn_starts_match_transcript_prefixes(self):
        for name in ("transcript.txt", "transcript-clean.txt"):
            parsed = bh.parse_transcript(T / name)
            self.assertEqual(len(parsed), EXPECTED_TURNS, name)
            for t, (prefix, rest) in zip(self.turns, parsed):
                self.assertEqual(prefix, t["start_hms"], f"{name} turn {t['turn_id']}")
                self.assertEqual(prefix, bh.hms(t["start_sec"]))
                self.assertTrue(rest.startswith(bh.display_name(t["speaker_name"], t["speaker_role"],
                                                                t["confidence"]) + ": "))

    def test_turns_csv(self):
        with open(T / "turns.csv", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            self.assertEqual(r.fieldnames, bh.TURN_FIELDS)
            rows = list(r)
        self.assertEqual(len(rows), EXPECTED_TURNS)
        for row, t in zip(rows, self.turns):
            self.assertIn(row["confidence"], bh.VALID_CONFIDENCE)
            self.assertLess(float(row["start_sec"]), float(row["end_sec"]))
            self.assertEqual(row["text_clean"], t["text_clean"])
            self.assertTrue(row["text_clean"].strip() and row["text_unedited"].strip())
        starts = [float(r["start_sec"]) for r in rows]
        self.assertEqual(starts, sorted(starts))

    def test_words_inside_turns(self):
        words = json.loads((T / "words.json").read_text(encoding="utf-8"))
        self.assertGreater(len(words), 80000)
        bounds = {t["turn_id"]: (t["start_sec"], t["end_sec"]) for t in self.turns}
        for w in words:
            s, e = bounds[w["turn_id"]]
            self.assertGreaterEqual(w["start"], s - EPS, w)
            self.assertLessEqual(w["end"], e + EPS, w)
            self.assertLessEqual(w["start"], w["end"], w)

    def test_captions_vtt(self):
        text = (T / "captions.vtt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("WEBVTT\n"))
        cue_re = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3}) --> (\d\d):(\d\d):(\d\d)\.(\d{3})$", re.MULTILINE)
        times = []
        for m in cue_re.finditer(text):
            g = [int(x) for x in m.groups()]
            times.append((g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000))
        self.assertGreater(len(times), 5000)
        long_cues = 0
        for i, (s, e) in enumerate(times):
            self.assertLessEqual(s, e, f"cue {i + 1}")
            if i:
                self.assertGreaterEqual(s, times[i - 1][0], f"cue {i + 1} starts before previous")
                self.assertGreaterEqual(s, times[i - 1][1] - 0.0005, f"cue {i} overlaps cue {i + 1}")
            if e - s > bh.MAX_CUE_SEC + 1.5:
                long_cues += 1
        self.assertLess(long_cues / len(times), 0.01, "too many cues over ~7 s")
        blocks = [b for b in text.split("\n\n") if cue_re.search(b)]
        for b in blocks:
            lines = b.split("\n")
            self.assertLessEqual(len(lines) - 2, 2, b)  # id, timing, then at most 2 text lines
            self.assertTrue(lines[2].startswith("<v "), b)

    def test_speakers_sum(self):
        with open(H / "speakers.csv", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            self.assertEqual(r.fieldnames, bh.SPEAKER_FIELDS)
            rows = list(r)
        total = sum(float(x["talk_seconds"]) for x in rows)
        expected = sum(t["end_sec"] - t["start_sec"] for t in self.turns)
        self.assertAlmostEqual(total, expected, delta=1.0)
        self.assertEqual(sum(int(x["turns"]) for x in rows), EXPECTED_TURNS)
        for x in rows:
            self.assertIn(x["category"], bh.CATEGORIES)

    def test_hearing_json(self):
        h = json.loads((H / "hearing.json").read_text(encoding="utf-8"))
        self.assertEqual(h["legistar"]["event_id"], 22752)
        self.assertEqual(len(h["bills"]), 10)
        self.assertEqual(h["stats"]["turns"], EXPECTED_TURNS)
        self.assertEqual(sum(h["stats"]["confidence_counts"].values()), EXPECTED_TURNS)

    def test_legistar_manifest(self):
        with open(H / "legistar" / "manifest.csv", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            self.assertEqual(r.fieldnames, bh.MANIFEST_FIELDS)
            rows = list(r)
        self.assertTrue(rows)
        for row in rows:
            p = H / "legistar" / row["filename"]
            self.assertTrue(p.is_file(), row["filename"])
            self.assertEqual(p.stat().st_size, int(row["bytes"]))
            self.assertTrue(row["legistar_url"].startswith("https://nyc.legistar1.com/"))
        on_disk = {p.name for p in (H / "legistar").iterdir()} - {"manifest.csv"}
        self.assertEqual(on_disk, {r["filename"] for r in rows})

    def test_all_files_under_100mb(self):
        for p in REPO.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                self.assertLess(p.stat().st_size, bh.MAX_FILE_BYTES, str(p))

    def test_index_relative_links_resolve(self):
        html_text = (REPO / "index.html").read_text(encoding="utf-8")
        links = relative_links(html_text)
        self.assertGreater(len(links), 20)
        for link in links:
            self.assertTrue((REPO / link).is_file(), link)

    def test_index_accessibility_basics(self):
        html_text = (REPO / "index.html").read_text(encoding="utf-8")
        p = LinkParser()
        p.feed(html_text)
        self.assertEqual(p.lang, "en")
        self.assertTrue(all(img.get("alt") for img in p.imgs))
        self.assertEqual(p.headings.count(1), 1)
        for a, b in zip(p.headings, p.headings[1:]):
            self.assertLessEqual(b, a + 1, f"heading level skips h{a} -> h{b}")
        self.assertIn('role="img"', html_text)
        self.assertRegex(html_text, r"<svg[^>]+aria-labelledby=")
        self.assertIn("<title id=", html_text)
        self.assertIn("<desc id=", html_text)


class ServeTests(unittest.TestCase):
    """Serve the repo root as GitHub Pages would and fetch every relative link."""

    def test_served_links_return_200(self):
        handler = functools.partial(QuietHandler, directory=str(REPO))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            base = f"http://127.0.0.1:{srv.server_address[1]}/"
            with urllib.request.urlopen(base + "index.html", timeout=10) as r:
                self.assertEqual(r.status, 200)
                body = r.read().decode("utf-8")
            links = relative_links(body)
            for link in links:
                req = urllib.request.Request(base + urllib.parse.quote(link), method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as r:
                    self.assertEqual(r.status, 200, link)
            print(f"\n  served index.html + {len(links)} relative links: all 200", file=sys.stderr)
        finally:
            srv.shutdown()
            srv.server_close()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    unittest.main()
