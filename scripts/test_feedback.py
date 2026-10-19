"""Every generated page carries the report-a-mistake footer link (scripts/feedback.py), and the
link fits the correction form. Standard library only, no network.

Run from the repository root:  python3 -m unittest discover -s scripts -v
"""

from __future__ import annotations

import html
import json
import re
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feedback as fb  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FORM = REPO / ".github" / "ISSUE_TEMPLATE" / fb.TEMPLATE
LINK = re.compile(r'<footer><div class="wrap"><p class="feedback">[^<]*<a href="([^"]+)">Open an issue on GitHub</a>')


def generated_pages() -> list[Path]:
    """Every HTML page the builds write: index.html, and each hearing's panels, word cloud and
    City Q&A pages."""
    pages = [REPO / "index.html"]
    for h in sorted((REPO / "hearings").glob("*/hearing.json")):
        pages += sorted(h.parent.rglob("*.html"))
    return pages


def link_params(page: Path) -> tuple[str, dict]:
    m = LINK.search(page.read_text(encoding="utf-8"))
    if not m:
        raise AssertionError(f"{page.relative_to(REPO)}: no feedback link in the footer")
    url = html.unescape(m.group(1))
    base, _, query = url.partition("?")
    return base, {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}


class FeedbackLink(unittest.TestCase):
    def test_every_page_type_is_covered(self):
        names = {p.name for p in generated_pages()} | {p.parent.name for p in generated_pages()}
        for expected in ("index.html", "panels.html", "city-qa.html", "wordclouds", "people"):
            self.assertIn(expected, names)

    def test_every_page_has_the_link_with_its_own_page_and_hearing(self):
        for page in generated_pages():
            rel = page.relative_to(REPO).as_posix()
            base, q = link_params(page)
            self.assertEqual(base, fb.ISSUES_NEW, rel)
            self.assertEqual(q["template"], "correction.yml", rel)
            self.assertEqual(q["page"], fb.SITE + rel, rel)
            self.assertIn(rel, q["title"], rel)
            self.assertNotIn("labels", q, rel)
            if rel == "index.html":
                self.assertNotIn("hearing", q)
            else:
                slug = rel.split("/")[1]
                h = json.loads((REPO / "hearings" / slug / "hearing.json").read_text(encoding="utf-8"))
                self.assertEqual(q["hearing"], f"{h['date']}, {h['body']}: {h['title']}", rel)

    def test_url_encoding_round_trips(self):
        h = {"date": "2026-10-16", "body": "NYC Council Committee on Technology",
             "title": "Risks & benefits: a \"test\" #1 / 50%"}
        url = fb.issue_url("hearings/x/panels.html", h)
        self.assertNotIn(" ", url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.split("?", 1)[1]).items()}
        self.assertEqual(q["hearing"], "2026-10-16, NYC Council Committee on Technology: Risks & benefits: a \"test\" #1 / 50%")
        self.assertIn("&amp;", fb.feedback_html("index.html", None))

    def test_form_exists_and_has_the_prefilled_field_ids(self):
        text = FORM.read_text(encoding="utf-8")
        for key in ("name:", "description:", "body:"):
            self.assertRegex(text, rf"(?m)^{key}")
        ids = re.findall(r"(?m)^\s+id: (\S+)$", text)
        self.assertIn(fb.FIELD_HEARING, ids)
        self.assertIn(fb.FIELD_PAGE, ids)
        for field in ("problem", "correction", "source"):
            self.assertIn(field, ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_readme_explains_corrections(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Corrections", readme)
        self.assertIn('href="README.md#corrections"', (REPO / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
