"""Tests for build_qa.py and the City Q&A page it built. Standard library only.

Run from the repository root:  python3 -m unittest discover -s scripts -v
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_qa as bq
from test_build import relative_links

REPO = Path(__file__).resolve().parent.parent
SLUG = "2026-10-05-committee-of-the-whole-ai"
H = REPO / "hearings" / SLUG
CFG_PATH = REPO / "scripts" / "meta" / f"{SLUG}-city-qa.json"
CFG = json.loads(CFG_PATH.read_text())
PAGE = H / CFG["page"]
TURNS = {t["turn_id"]: t for t in json.loads((H / "transcript" / "turns.json").read_text())}


class UnitTests(unittest.TestCase):
    def test_hms_to_sec(self):
        self.assertEqual(bq.hms_to_sec("05:33:03"), 5 * 3600 + 33 * 60 + 3)

    def test_turn_at_picks_the_turn_speaking(self):
        ts = [{"turn_id": 1, "start_sec": 0}, {"turn_id": 2, "start_sec": 100}, {"turn_id": 3, "start_sec": 200}]
        self.assertEqual(bq.turn_at(ts, "00:01:40")["turn_id"], 2)
        self.assertEqual(bq.turn_at(ts, "00:03:18")["turn_id"], 2)
        self.assertEqual(bq.turn_at(ts, "00:03:19")["turn_id"], 3)  # one second of slack for rounded times
        self.assertEqual(bq.turn_at(ts, "00:00:00")["turn_id"], 1)


class ConfigTests(unittest.TestCase):
    def all_ids(self) -> list[int]:
        by_id = TURNS
        ids = list(CFG["opening"]["turns"])
        for s in CFG["sections"]:
            ids += [t["turn_id"] for t in bq.section_turns(by_id, s)]
        return ids

    def test_no_turn_shown_twice(self):
        ids = self.all_ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_turn_exists_and_is_inside_the_panel(self):
        lo, hi = bq.hms_to_sec(CFG["panel"]["start_hms"]), bq.hms_to_sec(CFG["panel"]["end_hms"])
        for i in self.all_ids():
            self.assertIn(i, TURNS)
            self.assertTrue(lo <= TURNS[i]["start_sec"] <= hi, i)

    def test_question_times_fall_inside_their_section(self):
        for s in CFG["sections"]:
            ts = bq.section_turns(TURNS, s)
            for hms, _ in s["questions"]:
                sec = bq.hms_to_sec(hms)
                self.assertTrue(ts[0]["start_sec"] - 1 <= sec <= ts[-1]["end_sec"], (s["id"], hms))

    def test_officials_spoke(self):
        spoke = {t["speaker_name"] for t in TURNS.values()}
        for o in CFG["officials"]:
            if o["name"] != "Carlos Ortiz":
                self.assertIn(o["name"], spoke)

    def test_section_ids_unique(self):
        ids = [s["id"] for s in CFG["sections"]]
        self.assertEqual(len(ids), len(set(ids)))


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text()

    def test_page_is_current(self):
        before = self.html
        bq.build(CFG_PATH)
        self.assertEqual(PAGE.read_text(), before, "city-qa.html is stale: rerun build_qa.py")

    def test_every_in_page_link_has_a_target(self):
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        for ref in re.findall(r'href="#([^"]+)"', self.html):
            self.assertIn(ref, ids)

    def test_relative_links_resolve(self):
        for rel in relative_links(self.html):
            self.assertTrue((PAGE.parent / rel).resolve().exists(), rel)

    def test_every_answer_is_verbatim(self):
        for tid, text in re.findall(r'<div class="turn[^"]*" id="t(\d+)">.*?<p>(.*?)</p>', self.html, re.S):
            import html as h
            self.assertEqual(h.unescape(text), TURNS[int(tid)]["text_clean"])

    def test_city_turns_are_shaded(self):
        names = {o["name"] for o in CFG["officials"]}
        for tid in re.findall(r'<div class="turn city" id="t(\d+)">', self.html):
            t = TURNS[int(tid)]
            self.assertTrue(t["speaker_name"] in names or str(tid) in CFG["speaker_notes"], tid)

    def test_linked_from_gallery_officials_and_home(self):
        for p, href in ((H / "wordclouds" / "index.html", "../city-qa.html"),
                        (H / "wordclouds" / "city-officials.html", "../city-qa.html"),
                        (REPO / "index.html", f"hearings/{SLUG}/city-qa.html")):
            self.assertIn(f'href="{href}"', p.read_text(), p)


if __name__ == "__main__":
    unittest.main()
