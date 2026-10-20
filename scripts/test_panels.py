"""Tests for build_panels.py, panels.json checks in build_hearing.py, per-hearing word cloud
configs, and the built 2026-10-16 hearing. Standard library only, no network.

Run from the repository root:  python3 -m unittest discover -s scripts -v
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from unittest import mock
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hearing as bh  # noqa: E402
import build_panels as bp  # noqa: E402
import build_wordclouds as bw  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SLUG = "2026-10-16-technology-ai"
H = REPO / "hearings" / SLUG
PAGE = H / "panels.html"
EPS = 0.01


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.turns, self.links, self.srcs, self.ids = [], [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "g" and "turn" in (a.get("class") or "").split():
            self.turns.append(a)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("link", "script", "img") and (a.get("href") or a.get("src")):
            self.srcs.append(a.get("href") or a.get("src"))
        if a.get("id"):
            self.ids.append(a["id"])


def parsed_page() -> Collect:
    c = Collect()
    c.feed(PAGE.read_text(encoding="utf-8"))
    return c


def turns_csv() -> list[dict]:
    with open(H / "transcript" / "turns.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class PureFunctions(unittest.TestCase):
    TURNS = {0: {"i": 0, "start": 0.0, "end": 10.0, "name": "A", "role": "Speaker", "cat": "council", "text": "x"},
             1: {"i": 1, "start": 12.0, "end": 42.0, "name": "B", "role": "Witness — SpaceXAI", "cat": "ai-company", "text": "y"},
             2: {"i": 2, "start": 43.0, "end": 45.5, "name": "A", "role": "Speaker", "cat": "council", "text": "z"},
             3: {"i": 3, "start": 46.0, "end": 47.0, "name": "C", "role": "Committee Counsel", "cat": "council-staff", "text": "w"}}

    def test_panel_stats_sums_turn_times_and_sides(self):
        panel = {"turn_ids": [0, 1, 2, 3], "members": [{"name": "A", "role": "Speaker", "org": "NYC Council"},
                                                       {"name": "D", "role": "Witness", "org": "X"}]}
        st = bp.panel_stats(panel, self.TURNS)
        self.assertEqual([(p["name"], p["turns"], p["seconds"]) for p in st["people"]],
                         [("B", 1, 30.0), ("A", 2, 12.5), ("C", 1, 1.0)])
        self.assertEqual(st["sides"], {"Council Members": 12.5, "Council staff": 1.0, "Witnesses": 30.0,
                                       "Unidentified": 0.0})
        self.assertEqual(st["total"], 43.5)
        self.assertEqual([m["name"] for m in st["unheard"]], ["D"])

    def test_speaker_rows_follow_category_order_then_first_heard(self):
        rows = bp.speaker_rows(list(self.TURNS.values()))
        self.assertEqual([c for c, _ in rows], ["council", "ai-company", "council-staff"])

    def test_band_label_shortens_then_falls_back_to_number(self):
        self.assertEqual(bp.band_label("Panel 1: SpaceXAI (affirmation)", 400, 2), "Panel 1: SpaceXAI")
        self.assertEqual(bp.band_label("Panel 2: Devin Kim, former xAI employee (Zoom)", 150, 3), "Panel 2")
        self.assertEqual(bp.band_label("Opening statements", 40, 1), "1")
        self.assertEqual(bp.band_label("Closing", 10, 6), "")

    def test_script_data_cannot_break_out(self):
        out = bp.json_for_script([{"t": "a <!-- b </script> c"}])
        self.assertNotIn("<", out)
        self.assertEqual(__import__("json").loads(out), [{"t": "a <!-- b </script> c"}])

    def test_formatting(self):
        self.assertEqual(bp.clock(125.4), "2:05")
        self.assertEqual(bp.clock(3725), "1:02:05")
        self.assertEqual(bp.hms_to_sec("01:09:36"), 4176)
        self.assertEqual(bp.tick_step(7048), 600)
        self.assertEqual(bp.tick_step(36492), 3600)
        self.assertEqual(bp.first_words("one two three", 2), "one two …")

    def test_every_build_hearing_category_has_a_color(self):
        self.assertEqual(set(bh.CATEGORIES), set(bp.CAT_COLOR))

    def test_check_panels_rejects_bad_files(self):
        ok = [{"panel_id": "a", "title": "A", "start_hms": "00:00:00", "end_hms": "00:01:00", "turn_ids": [0, 1],
               "members": [{"name": "X", "role": "Speaker", "org": "NYC Council"}]}]
        bh.check_panels(ok, 2)
        bad_cases = [
            [{**ok[0], "turn_ids": [0, 5]}],                                  # out of range
            ok + [{**ok[0], "panel_id": "b", "turn_ids": [1]}],               # turn in two panels
            [{k: v for k, v in ok[0].items() if k != "members"}],             # missing key
            [{**ok[0], "members": [{"name": "X"}]}],                          # member keys
            [{**ok[0], "start_hms": "00:05:00", "turn_ids": [0]},
             {**ok[0], "panel_id": "b", "start_hms": "00:01:00", "turn_ids": [1]}],  # out of order
        ]
        for case in bad_cases:
            with self.assertRaises(SystemExit, msg=case):
                bh.check_panels(case, 2)

    def test_clock_12h(self):
        self.assertEqual(bh.clock_12h("11:00"), "11:00 AM")
        self.assertEqual(bh.clock_12h("10:00"), "10:00 AM")
        self.assertEqual(bh.clock_12h("14:30"), "2:30 PM")
        self.assertEqual(bh.clock_12h("00:15"), "12:15 AM")


class PanelsPage(unittest.TestCase):
    def test_every_turn_drawn_once_in_time_order(self):
        rows = turns_csv()
        drawn = [int(a["data-i"]) for a in parsed_page().turns]
        self.assertEqual(sorted(drawn), [int(r["turn_id"]) for r in rows])
        starts = {int(r["turn_id"]): float(r["start_sec"]) for r in rows}
        self.assertEqual([starts[i] for i in drawn], sorted(starts[i] for i in drawn))

    def test_turn_marks_are_keyboard_reachable_and_labeled(self):
        for a in parsed_page().turns:
            self.assertEqual(a.get("tabindex"), "0")
            self.assertEqual(a.get("role"), "button")
            self.assertRegex(a.get("aria-label", ""), r"^.+, \d\d:\d\d:\d\d to \d\d:\d\d:\d\d, ")

    def test_bars_stay_inside_the_plot(self):
        text = PAGE.read_text(encoding="utf-8")
        for x, w in re.findall(r'class="mark" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', text):
            self.assertGreaterEqual(float(x), bp.LABEL_W - EPS)
            self.assertLessEqual(float(x) + float(w), bp.W - bp.RIGHT_PAD + 2 + EPS)
            self.assertGreaterEqual(float(w), 2.0)

    def test_self_contained(self):
        c = parsed_page()
        external = [s for s in c.srcs if re.match(r"(https?:)?//", s)]
        self.assertEqual(external, [], "no external stylesheets, scripts or images")

    def test_relative_links_resolve_and_ids_unique(self):
        c = parsed_page()
        for href in c.links:
            if re.match(r"(https?:|mailto:|#)", href):
                continue
            path = href.split("#")[0]
            self.assertTrue((PAGE.parent / path).resolve().exists(), href)
        self.assertEqual(len(c.ids), len(set(c.ids)))
        for href in c.links:
            if href.startswith("#"):
                self.assertIn(href[1:], c.ids, href)

    def test_panel_talk_time_matches_turns(self):
        rows = {int(r["turn_id"]): r for r in turns_csv()}
        panels = json.loads((H / "panels.json").read_text(encoding="utf-8"))
        text = PAGE.read_text(encoding="utf-8")
        for k, p in enumerate(panels):
            secs = sum(float(rows[i]["end_sec"]) - float(rows[i]["start_sec"]) for i in p["turn_ids"])
            self.assertIn(f"{len(p['turn_ids'])} turns · {bp.clock(secs)} of talk", text, p["panel_id"])

    def test_method_note_and_disclosure(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn(bp.esc(bp.DISCLOSURE), text)
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("Names were assigned by AI agents working from these sources, at BetaNYC's direction.", readme)
        mixed = json.loads((H / "hearing.json").read_text(encoding="utf-8"))["mixed_turns"]
        self.assertIn(f"{mixed} of the 248 turns hold two speakers", text)
        self.assertIn("Times are seconds from the start of the Council's recording", text)

    def test_linked_from_index_and_readme(self):
        self.assertIn(f'href="hearings/{SLUG}/panels.html"', (REPO / "index.html").read_text(encoding="utf-8"))
        self.assertIn("[`panels.html`](panels.html)", (H / "README.md").read_text(encoding="utf-8"))

    def test_build_is_idempotent(self):
        before = PAGE.read_bytes()
        bp.build(SLUG)
        self.assertEqual(PAGE.read_bytes(), before)


class Hearing20261016(unittest.TestCase):
    def test_turns_and_transcript_prefixes(self):
        rows = turns_csv()
        self.assertEqual(len(rows), 248)
        for name in ("transcript.txt", "transcript-clean.txt"):
            parsed = bh.parse_transcript(H / "transcript" / name)
            self.assertEqual([h for h, _ in parsed], [r["start_hms"] for r in rows], name)

    def test_categories_and_speakers(self):
        with open(H / "speakers.csv", encoding="utf-8", newline="") as f:
            sp = {r["speaker_name"]: r for r in csv.DictReader(f)}
        self.assertEqual(sp["Gabriela Castillo Madrid"]["category"], "ai-company")
        self.assertEqual(sp["Devin Kim"]["category"], "witness")
        self.assertEqual(sp["Julie Menin"]["category"], "council")
        total = sum(float(r["talk_seconds"]) for r in sp.values())
        turns = sum(float(r["end_sec"]) - float(r["start_sec"]) for r in turns_csv())
        self.assertAlmostEqual(total, turns, delta=0.5)

    def test_hearing_json_and_media_state(self):
        """2026-10-19: the MP3 Release is published; the Internet Archive item is uploaded but not
        yet playable, so it is linked as a copy and the Council's video stays the Watch button."""
        h = json.loads((H / "hearing.json").read_text(encoding="utf-8"))
        self.assertEqual(h["legistar"]["event_id"], 22795)
        mp3 = h["media"]["audio_mp3"]
        self.assertTrue(mp3["release_published"])
        self.assertEqual(mp3["release_url"],
                         "https://github.com/BetaNYC/hearings-transcripts/releases/tag/2026-10-16-technology-ai")
        ia = "https://archive.org/details/nyc-council-technology-ai-2026-10-16"
        self.assertEqual(h["video"]["internet_archive_url"], ia)
        self.assertFalse(h["video"]["archive_playable"])
        media = (H / "media" / "README.md").read_text(encoding="utf-8")
        self.assertIn(mp3["release_url"], media)
        self.assertNotIn("not published yet", media)
        self.assertIn(ia + " " + bh.ARCHIVE_PENDING_NOTE, media)
        readme = (H / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"- Internet Archive copy: [archive.org]({ia})", readme)
        self.assertNotIn("- Watch: [Internet Archive]", readme)
        self.assertNotIn("has not been published as a GitHub Release", readme)
        card = (REPO / "index.html").read_text(encoding="utf-8").split(f'id="h-{SLUG}"', 1)[1].split("</article>", 1)[0]
        self.assertIn(f'<a class="button" href="{bh.esc(h["video"]["council_source_url"])}">Watch the Council', card)
        self.assertNotIn("Watch on the Internet Archive", card)
        self.assertIn(f'<a href="{ia}">Internet Archive copy</a>', card)
        self.assertIn(bh.esc(bh.ARCHIVE_PENDING_NOTE), card)
        self.assertIn(f'<a href="{mp3["release_url"]}">Audio, full quality (GitHub Release)</a>', card)
        self.assertTrue((H / "media" / "hearing-audio-16k.opus").is_file())
        self.assertFalse(any(H.rglob("*.mp3")) or any(H.rglob("*.mp4")))

    def test_index_card_has_no_empty_links(self):
        text = (REPO / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href=""', text)

    def test_legistar_manifest(self):
        with open(H / "legistar" / "manifest.csv", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r["filename"] for r in rows}, {"meeting-agenda.pdf", "t2026-2684-committee-report.docx"})
        for r in rows:
            self.assertEqual((H / "legistar" / r["filename"]).stat().st_size, int(r["bytes"]))


class QaRound1(unittest.TestCase):
    """Regression checks for the 2026-10-19 QA round on the 2026-10-16 hearing."""

    def test_readme_matches_current_meta(self):
        text = (H / "README.md").read_text(encoding="utf-8")
        self.assertIn("not 10:00 AM", text)
        self.assertNotIn("shown only for the Speaker", text)
        self.assertIn("Zoom name label", text)
        self.assertIn("scripts/meta/2026-10-16-technology-ai-wordclouds.json", text)
        self.assertIn("were not reviewed by hand", text)
        self.assertNotIn("still in progress", text)
        h = json.loads((H / "hearing.json").read_text(encoding="utf-8"))
        self.assertIn("naming_sources", h)
        self.assertNotIn("Chair", {p["role"] for p in h["council_members_present"]})

    def test_mixed_column(self):
        rows = turns_csv()
        self.assertEqual({r["mixed"] for r in rows}, {"true", "false"})
        h = json.loads((H / "hearing.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(r["mixed"] == "true" for r in rows), h["mixed_turns"])
        js = json.loads((H / "transcript" / "turns.json").read_text(encoding="utf-8"))
        self.assertTrue(all(isinstance(t["mixed"], bool) for t in js))

    def test_unverified_firm_and_labels_removed(self):
        for p in [H / "speakers.csv", H / "panels.json", H / "transcript" / "turns.csv",
                  H / "transcript" / "transcript.txt", H / "transcript" / "transcript-clean.txt",
                  REPO / "index.html", PAGE]:
            text = p.read_text(encoding="utf-8")
            # Verified 2026-10-19: the firm may appear as an org or in her own words, never as a role.
            self.assertNotIn("Witness — Sanford", text, p.name)
        # "whistleblower" is spoken in the hearing; it must not be a label in this hearing's data.
        for p in [H / "speakers.csv", H / "panels.json"]:
            self.assertNotIn("whistleblower", p.read_text(encoding="utf-8").lower(), p.name)
        self.assertIn("Qiaojing Ella Zheng (counsel to Devin Kim):", (H / "transcript" / "transcript.txt").read_text(encoding="utf-8"))
        self.assertIn("panel-2-devin-kim", (H / "panels.json").read_text(encoding="utf-8"))
        clean = (H / "transcript" / "transcript-clean.txt").read_text(encoding="utf-8")
        self.assertIn("partner at Sanford Heisler Sharp McKnight", clean)
        members = {m["name"]: m for p in json.loads((H / "panels.json").read_text(encoding="utf-8")) for m in p["members"]}
        self.assertEqual(members["Qiaojing Ella Zheng"]["role"], "Witness — counsel to Devin Kim")
        self.assertEqual(members["Qiaojing Ella Zheng"]["org"], "Sanford Heisler Sharp McKnight")
        readme = (H / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("no firm is given", readme)
        for phrase in ("no surname was found", "Sophie Cody", "as stated at the hearing", "former xAI employee"):
            self.assertIn(phrase, readme)
        self.assertIn("Witness — Demilitarize Brooklyn Navy Yard", (H / "speakers.csv").read_text(encoding="utf-8"))

    def test_council_member_won_in_clean_text(self):
        clean = (H / "transcript" / "transcript-clean.txt").read_text(encoding="utf-8")
        self.assertIn("Council Member Won.", clean)
        self.assertNotIn("Council Member Wong", clean)

    def test_index_chart_counts_speakers(self):
        text = (REPO / "index.html").read_text(encoding="utf-8")
        self.assertIn("All 17 speakers by total talk time", text)
        self.assertIn("Top 25 of 106 speakers by total talk time", text)
        self.assertIn(f'<title id="chart-title-{SLUG}">All 17 speakers by talk time</title>', text)
        self.assertIn('>Top 25 of 106 speakers by talk time</title>', text)

    def test_remote_panels_marked_zoom(self):
        titles = {p["panel_id"]: p["title"] for p in json.loads((H / "panels.json").read_text(encoding="utf-8"))}
        self.assertIn("(Zoom)", titles["panel-1-spacexai"])


class IndexToc(unittest.TestCase):
    def test_index_lists_every_hearing_newest_first(self):
        text = (REPO / "index.html").read_text(encoding="utf-8")
        toc = text.split('<nav aria-labelledby="toc-h"', 1)[1].split("</nav>", 1)[0]
        hearings = sorted(((json.loads(p.read_text(encoding="utf-8"))["date"], p.parent.name)
                           for p in (REPO / "hearings").glob("*/hearing.json")), reverse=True)
        self.assertGreaterEqual(len(hearings), 2)
        linked = re.findall(r'<th scope="row"><a href="#h-([^"]+)">', toc)
        self.assertEqual(linked, [slug for _, slug in hearings])
        dates = re.findall(r'<td class="nowrap">(\d{4}-\d{2}-\d{2})</td>', toc)
        self.assertEqual(dates, [d for d, _ in hearings])
        for _, slug in hearings:
            self.assertIn(f'id="h-{slug}"', text)
            self.assertIn(f'href="{bh.repo_blob(f"hearings/{slug}/README.md")}"', toc)
        self.assertIn(f'href="hearings/{SLUG}/panels.html"', toc)
        self.assertIn('href="hearings/2026-10-05-committee-of-the-whole-ai/city-qa.html"', toc)
        self.assertLess(text.index('id="toc-h"'), text.index("<h2>Each hearing</h2>"))


class WordcloudConfigs(unittest.TestCase):
    def test_explicit_config_is_used_not_ignored(self):
        with mock.patch.object(bw, "build") as build:
            bw.main(["--slug", SLUG, "--config", str(bw.DEFAULT_CONFIG)])
        self.assertEqual(build.call_args.args[1]["_path"], bw.DEFAULT_CONFIG)
        with mock.patch.object(bw, "build") as build:
            bw.main(["--slug", SLUG])
        self.assertEqual(build.call_args.args[1]["_path"].name, f"{SLUG}-wordclouds.json")

    def test_hearing_config_is_picked_and_extends_the_default(self):
        path = bw.config_for(SLUG, bw.DEFAULT_CONFIG)
        self.assertEqual(path.name, f"{SLUG}-wordclouds.json")
        self.assertEqual(bw.config_for("2026-10-05-committee-of-the-whole-ai", bw.DEFAULT_CONFIG), bw.DEFAULT_CONFIG)
        cfg = bw.load_config(path)
        base = bw.load_config(bw.DEFAULT_CONFIG)
        self.assertEqual(cfg["stopwords"], base["stopwords"])
        self.assertEqual([g["slug"] for g in cfg["groups"]], ["council-members", "spacexai", "witnesses"])
        self.assertNotIn("gallery_disclosure", cfg, "the 2026-10-05 BetaNYC disclosure must not carry over")

    def test_pages_say_this_hearing_was_not_reviewed_by_hand(self):
        page = (H / "wordclouds" / "spacexai.html").read_text(encoding="utf-8")
        self.assertIn("This hearing&#x27;s lists were not reviewed by hand.", page)
        self.assertNotIn("BetaNYC, which built these pages, testified", (H / "wordclouds" / "index.html").read_text(encoding="utf-8"))
        for p in ("gabriela-castillo-madrid", "devin-kim", "julie-menin", "carmen-de-la-rosa"):
            self.assertTrue((H / "wordclouds" / "people" / f"{p}.html").is_file(), p)



class Audits20261019(unittest.TestCase):
    """Regression checks for the 2026-10-19 docs audit (M3, M4) and numbers audit (D1-D6)."""

    OCT5 = REPO / "hearings" / "2026-10-05-committee-of-the-whole-ai"

    def index(self) -> str:
        return (REPO / "index.html").read_text(encoding="utf-8")

    def card(self, slug: str) -> str:
        return self.index().split(f'id="h-{slug}"', 1)[1].split("</article>", 1)[0]

    def test_human_dur_never_shows_zero_minutes(self):  # D5
        self.assertEqual(bh.human_dur(10.48), "10s")
        self.assertEqual(bh.human_dur(16.18), "16s")
        self.assertEqual(bh.human_dur(0.4), "0s")
        self.assertEqual(bh.human_dur(60), "1m")
        self.assertEqual(bh.human_dur(1648.78), "27m")
        self.assertEqual(bh.human_dur(3600), "1h 00m")
        self.assertNotIn(">0m<", self.index())

    def test_chart_title_pluralizes_turns(self):  # D5
        sp = [{"speaker_name": "A", "speaker_role": "Council Member", "category": "council",
               "turns": 1, "talk_seconds": 30.0},
              {"speaker_name": "B", "speaker_role": "Council Member", "category": "council",
               "turns": 2, "talk_seconds": 90.0}]
        svg = bh.chart_svg(sp, "x")
        self.assertIn("in 1 turn</title>", svg)
        self.assertIn("in 2 turns</title>", svg)
        self.assertNotIn("in 1 turns", self.index())

    def test_panel_share_below_half_percent(self):  # D5
        self.assertEqual(bp.share(10.48, 3439.99), "<1%")
        self.assertEqual(bp.share(0, 100), "0%")
        self.assertEqual(bp.share(30.0, 100), "30%")
        self.assertIn("Council staff 0:10 (&lt;1%)", PAGE.read_text(encoding="utf-8"))

    def test_top_two_tie_note(self):  # D1
        def sp(name, secs):
            return {"speaker_name": name, "speaker_role": "R", "talk_seconds": secs}
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            hdir = Path(d)
            (hdir / "transcript").mkdir()
            fields = ["turn_id", "start_sec", "end_sec", "speaker_name", "speaker_role", "mixed"]
            with open(hdir / "transcript" / "turns.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerow({"turn_id": 0, "start_sec": 0, "end_sec": 100, "speaker_name": "A",
                            "speaker_role": "R", "mixed": "true"})
                w.writerow({"turn_id": 1, "start_sec": 100, "end_sec": 200, "speaker_name": "B",
                            "speaker_role": "R", "mixed": "false"})
            tied = bh.top_two_note(hdir, [sp("A", 1630), sp("B", 1600)])  # gap 30 s < 100 s mixed
            self.assertIn("A and B each spoke about 27 minutes", tied)
            self.assertIn("does not show which of them spoke longer", tied)
            self.assertEqual(bh.top_two_note(hdir, [sp("A", 1800), sp("B", 1600)]), "")  # gap 200 s
            self.assertIn("spoke about 30 and 28 minutes",
                          bh.top_two_note(hdir, [sp("A", 1790), sp("B", 1700)]))
        with tempfile.TemporaryDirectory() as d:  # no mixed column (2026-10-05): no claim either way
            hdir = Path(d)
            (hdir / "transcript").mkdir()
            (hdir / "transcript" / "turns.csv").write_text("turn_id,start_sec,end_sec,speaker_name,speaker_role\n"
                                                           "0,0,1,A,R\n", encoding="utf-8")
            self.assertEqual(bh.top_two_note(hdir, [sp("A", 1650), sp("B", 1600)]), "")

    def test_oct16_chart_does_not_rank_top_two(self):  # D1
        card = self.card(SLUG)
        self.assertIn("Julie Menin and Gabriela Castillo Madrid each spoke about 27 minutes", card)
        self.assertNotIn("each spoke about", self.card(self.OCT5.name))

    def test_wordcloud_pages_disclose_mixed_turns(self):  # D2
        for page in sorted((H / "wordclouds").rglob("*.html")):
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8")
                self.assertIn("56 turns at this hearing hold two voices", text)
                self.assertIn("count toward the person named on the turn", text)
                if page.name != "index.html":
                    self.assertRegex(text, r"On this page, [\d,]+ of the [\d,]+ words are in such turns")
        menin = (H / "wordclouds" / "people" / "julie-menin.html").read_text(encoding="utf-8")
        self.assertIn("On this page, 1,747 of the 3,979 words are in such turns", menin)  # numbers audit D2
        for page in sorted((self.OCT5 / "wordclouds").rglob("*.html")):
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8")
                self.assertIn("Some turns hold two voices", text)
                self.assertNotIn("On this page,", text)

    def test_mixed_words_counted_only_with_a_mixed_column(self):  # D2
        turns = [{"speaker_name": "A", "start_sec": "0", "end_sec": "60", "text_clean": "one two three",
                  "mixed": "true"},
                 {"speaker_name": "A", "start_sec": "60", "end_sec": "120", "text_clean": "four five",
                  "mixed": "false"}]
        st = bw.turn_stats(turns, lambda t: True)
        self.assertEqual((st["words"], st["mixed_words"]), (5, 3))
        old = [{k: v for k, v in t.items() if k != "mixed"} for t in turns]
        self.assertNotIn("mixed_words", bw.turn_stats(old, lambda t: True))
        self.assertIn("On this page, 3 of the 5 words", bw.mixed_note({"mixed_turns": 2}, st))
        self.assertTrue(bw.mixed_note({}, None).startswith("Some turns hold two voices"))

    def test_shared_how_made_covers_both_hearings(self):  # M3, D3
        text = self.index()
        self.assertNotIn("shown only for the Speaker", text)
        self.assertIn("Zoom name labels on 2026-10-16, read from video frames", text)
        self.assertIn("the Council&#x27;s captions", text)
        self.assertNotIn("Some turns are labeled Unidentified", text)
        self.assertIn("each hearing&#x27;s README gives the count", text)
        self.assertIn("includes short pauses inside a turn", text)

    def test_oct5_archive_copy_is_playable(self):  # M4
        h = json.loads((self.OCT5 / "hearing.json").read_text(encoding="utf-8"))
        self.assertTrue(h["video"]["archive_playable"])
        for f in (self.OCT5 / "README.md", self.OCT5 / "media" / "README.md"):
            self.assertNotIn("still in progress", f.read_text(encoding="utf-8"))
            self.assertNotIn(bh.ARCHIVE_PENDING_NOTE, f.read_text(encoding="utf-8"))
        card = self.card(self.OCT5.name)
        self.assertIn('Watch on the Internet Archive</a>', card)
        self.assertNotIn(bh.esc(bh.ARCHIVE_PENDING_NOTE), card)

    def test_archive_md_variants(self):  # M4
        meta = {"video": {"internet_archive_url": "", "archive_playable": False}}
        self.assertIn("has not been uploaded yet", bh.archive_md(meta))
        meta["video"]["internet_archive_url"] = "https://archive.org/details/x"
        self.assertTrue(bh.archive_md(meta).startswith("- Internet Archive copy: "))
        meta["video"]["archive_playable"] = True
        self.assertEqual(bh.archive_md(meta), "- Watch: [Internet Archive](https://archive.org/details/x)")

    def test_words_and_unquantified_mixed_wording(self):  # D4, D6
        for d in (H, self.OCT5):
            self.assertIn("words (unedited Deepgram transcript):", (d / "README.md").read_text(encoding="utf-8"))
        self.assertNotIn("a few turns", self.index())
        self.assertIn("this hearing&#x27;s labels do not mark or count them", self.card(self.OCT5.name))


if __name__ == "__main__":
    unittest.main()
