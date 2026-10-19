"""Tests for validate_clean.py. Standard library only, no network.

Run from the repository root:  python3 -m unittest discover -s scripts -v
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_clean as vc  # noqa: E402

UNEDITED = """Header line, ignored
Second header line

[00:00:10] Sergeant-at-Arms: Um, good morning, and and welcome.

[00:00:28] Speaker Julie Menin: I'm New York City council speaker Julie Menon. """ + "word " * 60 + """

[00:09:06] Gabriela Castillo Madrid (SpaceXAI): Yes.
"""
CLEAN_OK = """Header

[00:00:10] Sergeant-at-Arms: Good morning, and welcome.

[00:00:28] Speaker Julie Menin: I'm New York City Council Speaker Julie Menin. """ + "word " * 60 + """

[00:09:06] Gabriela Castillo Madrid (SpaceXAI): Yes.
"""


def run(a: str, b: str, *flags: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        pa, pb = Path(d) / "a.txt", Path(d) / "b.txt"
        pa.write_text(a, encoding="utf-8")
        pb.write_text(b, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vc.main([str(pa), str(pb), *flags])
    return code, out.getvalue()


class ValidateClean(unittest.TestCase):
    def test_headers_skipped_and_turns_split(self):
        self.assertEqual(len(vc.turns_of(UNEDITED)), 3)
        self.assertEqual(vc.pre(vc.turns_of(UNEDITED)[2]), "[00:09:06] Gabriela Castillo Madrid (SpaceXAI):")

    def test_matching_edit_passes(self):
        code, out = run(UNEDITED, CLEAN_OK)
        self.assertEqual(code, 0)
        self.assertIn("turns in=3 out=3 prefix_mismatch=0 changed=2", out)

    def test_changed_speaker_label_fails(self):
        code, out = run(UNEDITED, CLEAN_OK.replace("Speaker Julie Menin:", "CM Julie Menin:"))
        self.assertEqual(code, 1)
        self.assertIn("prefix_mismatch=1", out)

    def test_changed_timestamp_fails(self):
        self.assertEqual(run(UNEDITED, CLEAN_OK.replace("[00:09:06]", "[00:09:07]"))[0], 1)

    def test_dropped_turn_fails(self):
        dropped = CLEAN_OK.split("\n\n[00:09:06]")[0] + "\n"
        code, out = run(UNEDITED, dropped)
        self.assertEqual(code, 1)
        self.assertIn("out=2", out)

    def test_big_shrink_is_reported(self):
        code, out = run(UNEDITED, CLEAN_OK.replace("word " * 60, "word"))
        self.assertEqual(code, 0, "a shrink is a warning, not a failure")
        self.assertIn("big_shrinks=1", out)

    def test_names_lists_proper_noun_changes(self):
        _, out = run(UNEDITED, CLEAN_OK, "--names")
        self.assertIn("+Menin x1", out)
        self.assertIn("-Menon x1", out)

    def test_usage_without_two_paths(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(vc.main(["only-one.txt"]), 2)

    def test_unknown_flag_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(UNEDITED, CLEAN_OK, "--name")[0], 2)

    def test_whitespace_only_line_separates_turns_like_the_build(self):
        """A line holding only spaces separates two turns for build_hearing.py; the validator
        must see the same two turns, not one merged turn with the second one's text lost."""
        a = "[00:00:01] A: one.\n\n[00:00:05] B: two.\n"
        b = "[00:00:01] A: One.\n   \n[00:00:05] B: Two.\n"
        self.assertEqual(len(vc.turns_of(b)), 2)
        self.assertEqual(run(a, b)[0], 0)
        merged = "[00:00:01] A: One.\n[00:00:05] B: Two.\n"   # no separator at all: one turn
        self.assertEqual(run(a, merged)[0], 1)

    def test_missing_space_after_name_colon_fails(self):
        """build_hearing.py requires `Name: text`; `Name:text` must not pass here either."""
        code, out = run(UNEDITED, CLEAN_OK.replace("Sergeant-at-Arms: Good", "Sergeant-at-Arms:Good"))
        self.assertEqual(code, 1)
        self.assertIn("prefix_mismatch=1", out)

    def test_text_split_off_by_a_blank_line_fails_loudly(self):
        """Reviewer's case (2026-10-19): a whitespace-only line inside turn 0 cut off its last
        sentence, which vanished from turns.csv while the validator and the build both passed."""
        import build_hearing as bh
        broken = ("[00:00:10] Sergeant-at-Arms: Good morning, and welcome.\n   \n"
                  "Shahana, we're ready to begin.\n\n[00:00:28] Speaker Julie Menin: Good morning.\n")
        with self.assertRaises(ValueError) as cm:
            bh.parse_transcript_text(broken)
        self.assertIn("ready to begin", str(cm.exception))
        ok = "[00:00:10] Sergeant-at-Arms: Good morning.\n\n[00:00:28] Speaker Julie Menin: Hi.\n"
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(run(ok, broken)[0], 1)
        self.assertIn("is not a turn", err.getvalue())

    def test_header_before_first_turn_is_still_allowed(self):
        import build_hearing as bh
        self.assertEqual(len(bh.parse_transcript_text("Title\n\nNotes line\n\n[00:00:01] A: x\n")), 1)

    def test_validator_and_build_agree_on_turns(self):
        import build_hearing as bh
        self.assertEqual(len(vc.turns_of(UNEDITED)), len(bh.parse_transcript_text(UNEDITED)))


if __name__ == "__main__":
    unittest.main()
