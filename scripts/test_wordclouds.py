"""Tests for build_wordclouds.py and the pages it built. Standard library only.

Run from the repository root:  python3 -m unittest discover -s scripts -v

The phrase fixtures in tests/fixtures/wordclouds/ are the output of the approved prototype
(distinct.py, 2026-10-06), renamed to the group slugs. Each group's top 45 phrases, counts
and z-scores must match them exactly.
"""

from __future__ import annotations

import csv
import json
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hearing as bh
import build_wordclouds as bw
from test_build import relative_links

REPO = Path(__file__).resolve().parent.parent
SLUG = "2026-10-05-committee-of-the-whole-ai"
H = REPO / "hearings" / SLUG
WC = H / "wordclouds"
FIXTURES = REPO / "tests" / "fixtures" / "wordclouds"
CFG = bw.load_config(bw.DEFAULT_CONFIG)
GROUPS = [g["slug"] for g in CFG["groups"]]
PEOPLE = CFG["people"]
TOP = 45


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nav_links, self.current, self.ids = [], [], []
        self.svgs, self.focusable_static = [], 0
        self._in_nav = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "nav" and a.get("class") == "groups":
            self._in_nav = True
        if tag == "a" and self._in_nav:
            self.nav_links.append(a["href"])
            if a.get("aria-current") == "page":
                self.current.append(a["href"])
        if tag == "svg":
            self.svgs.append(a)

    def handle_endtag(self, tag):
        if tag == "nav":
            self._in_nav = False


def parse(path: Path) -> PageParser:
    p = PageParser()
    p.feed(path.read_text(encoding="utf-8"))
    p.close()
    return p


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        assert r.fieldnames == bw.CSV_FIELDS, r.fieldnames
        return list(r)


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = bw.compute(H, CFG)
        cls.turns = cls.res["turns"]
        cls.speakers = bw.read_csv(H / "speakers.csv")
        cls.cats = bw.category_map(cls.speakers)

    def members(self, slug):
        g = next(g for g in CFG["groups"] if g["slug"] == slug)
        m = bw.group_matcher(g["match"], self.cats)
        return {t["turn_id"] for t in self.turns if m(t)}

    def test_groups_nonempty_and_disjoint(self):
        seen = set()
        for slug in GROUPS:
            ids = self.members(slug)
            self.assertTrue(ids, slug)
            self.assertFalse(ids & seen, f"{slug} overlaps another group")
            seen |= ids

    def test_council_group_excludes_chairs(self):
        names = {t["speaker_name"] for t in self.turns if t["turn_id"] in self.members("council-members")}
        self.assertNotIn("Julie Menin", names)
        self.assertNotIn("Carmen De La Rosa", names)
        self.assertIn("Gale Brewer", names)

    def test_whistleblowers_only_in_their_panel(self):
        wb = {t["speaker_name"] for t in self.turns if t["turn_id"] in self.members("whistleblower-panel")}
        # the prototype also counted one unnamed voice labeled to the panel
        self.assertEqual({n for n in wb if not n.startswith("Unidentified")},
                         {"Jacob Coxon", "Daniel Kokotajlo", "Alex Turner"})
        pub = {t["speaker_name"] for t in self.turns if t["turn_id"] in self.members("public-witnesses")}
        self.assertFalse(wb & pub)

    def test_phrases_match_prototype_fixtures(self):
        for slug in GROUPS:
            fx = json.loads((FIXTURES / f"{slug}.json").read_text(encoding="utf-8"))["phrases"][:TOP]
            got = self.res["groups"][slug][0]["phrases"][:TOP]
            self.assertEqual([(x["phrase"], x["panel"], x["rest"], x["z"]) for x in fx],
                             [(x["phrase"], x["group_count"], x["others_count"], x["z"]) for x in got], slug)
            on_disk = read_rows(WC / f"{slug}.csv")[:TOP]
            self.assertEqual([x["phrase"] for x in fx], [r["phrase"] for r in on_disk], slug)

    def test_person_counts_only_their_turns(self):
        for p in PEOPLE:
            expected = sum(t["speaker_name"] == p["name"] for t in self.turns)
            stats = self.res["people"][p["slug"]][1]
            self.assertEqual(stats["turns"], expected, p["slug"])
            self.assertEqual(set(stats["speakers"]), {p["name"]})
            self.assertGreater(len(self.res["people"][p["slug"]][0]["phrases"]), 0, p["slug"])
            page = (WC / "people" / f"{p['slug']}.html").read_text(encoding="utf-8")
            self.assertIn(bw.plural(expected, "turn"), page)

    def test_person_min_count(self):
        for p in PEOPLE:
            rows = read_rows(WC / "people" / f"{p['slug']}.csv")
            self.assertTrue(all(int(r["group_count"]) >= CFG["people_method"]["min_person_count"] for r in rows))

    def test_tokenizer_and_filters(self):
        self.assertEqual(bw.tokens("OpenAI’s model's risks"), ["openai", "model", "risks"])
        stop = {"the"}
        g = bw.grams("the city. New York safety rules", stop, CFG["method"])
        self.assertNotIn("city", g)
        self.assertFalse(any("york" in x for x in g))
        self.assertIn("safety rules", g)

    def test_plural(self):
        self.assertEqual(bw.plural(1, "turn"), "1 turn")
        self.assertEqual(bw.plural(2, "turn"), "2 turns")
        self.assertEqual(bw.plural(1200, "word"), "1,200 words")


class PageTests(unittest.TestCase):
    def all_pages(self):
        return ([WC / f"{g}.html" for g in GROUPS] + [WC / "people" / f"{p['slug']}.html" for p in PEOPLE]
                + [WC / "index.html"])

    def test_pages_exist_parse_and_have_nav(self):
        for page in self.all_pages():
            self.assertTrue(page.is_file(), page)
            text = page.read_text(encoding="utf-8")
            self.assertNotIn("rototype", text, page)
            p = parse(page)
            self.assertEqual(len(p.nav_links), 6, page)
            for href in p.nav_links:
                self.assertTrue((page.parent / href).resolve().is_file(), f"{page.name}: {href}")
            self.assertEqual(len(p.ids), len(set(p.ids)), f"duplicate id in {page}")

    def test_group_page_marks_current(self):
        for g in GROUPS:
            p = parse(WC / f"{g}.html")
            self.assertEqual(p.current, [f"{g}.html"])

    def test_svg_accessibility(self):
        for page in self.all_pages()[:-1]:
            text = page.read_text(encoding="utf-8")
            p = parse(page)
            self.assertEqual(len(p.svgs), 2, page)
            for svg in p.svgs:
                self.assertIn("role", svg)
                t_id, d_id = svg["aria-labelledby"].split()
                self.assertIn(f'<title id="{t_id}">', text)
                self.assertIn(f'<desc id="{d_id}">', text)
            self.assertIn("tabindex:0", text)  # words and bars are keyboard-focusable

    def test_relative_links_resolve(self):
        pages = self.all_pages() + [REPO / "index.html"]
        for page in pages:
            links = relative_links(page.read_text(encoding="utf-8"))
            self.assertTrue(links, page)
            for link in links:
                self.assertTrue((page.parent / link).resolve().is_file(), f"{page}: {link}")

    def test_landing_and_readme_link_gallery(self):
        self.assertIn(f'href="hearings/{SLUG}/wordclouds/index.html"', (REPO / "index.html").read_text(encoding="utf-8"))
        self.assertIn("(wordclouds/index.html)", (H / "README.md").read_text(encoding="utf-8"))

    def test_readme_matches_full_build(self):
        """The README section added by --index-only equals what a full build would write."""
        meta = json.loads((H / "hearing.json").read_text(encoding="utf-8"))
        speakers = bw.read_csv(H / "speakers.csv")
        expected = bh.hearing_readme(meta, meta["stats"], speakers, bh.read_manifest(H))
        self.assertEqual((H / "README.md").read_text(encoding="utf-8"), expected)

    def test_gallery_links_every_group_and_person(self):
        text = (WC / "index.html").read_text(encoding="utf-8")
        for g in GROUPS:
            self.assertIn(f'href="{g}.html"', text)
        for p in PEOPLE:
            self.assertIn(f'href="people/{p["slug"]}.html"', text)
        self.assertIn("Individual speakers", text)

    def test_group_pages_link_their_people(self):
        for p in PEOPLE:
            self.assertIn(f'href="people/{p["slug"]}.html"', (WC / f"{p['group']}.html").read_text(encoding="utf-8"))
            person = (WC / "people" / f"{p['slug']}.html").read_text(encoding="utf-8")
            self.assertIn(f'href="../{p["group"]}.html"', person)
            self.assertIn('href="../index.html"', person)

    def test_csvs_parse(self):
        for path in list(WC.glob("*.csv")) + list((WC / "people").glob("*.csv")):
            rows = read_rows(path)
            self.assertTrue(rows, path)
            for r in rows:
                self.assertGreaterEqual(float(r["z"]), CFG["method"]["z_threshold"])  # z is rounded to 0.01
                int(r["group_count"]), int(r["others_count"])

    def test_files_under_100mb(self):
        for path in WC.rglob("*"):
            if path.is_file():
                self.assertLess(path.stat().st_size, bh.MAX_FILE_BYTES, path)

    def test_build_is_idempotent(self):
        before = {p: p.read_bytes() for p in WC.rglob("*") if p.is_file()}
        bw.build(SLUG, CFG)
        after = {p: p.read_bytes() for p in WC.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
