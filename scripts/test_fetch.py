"""Tests for the pure parts of fetch_legistar.py, fetch_media.py and render_deepgram_raw.py.

Standard library only, no network. Run from the repository root:
    python3 -m unittest discover -s scripts -v

Fixtures use the field names in the Legistar Web API reference (https://webapi.legistar.com/Help)
and values seen for event 22795 on 2026-10-19; the Viebit page fixture is cut down from the
2026-10-16 hearing's page.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_legistar as fl  # noqa: E402
import fetch_media as fm  # noqa: E402
import render_deepgram_raw as rd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

EVENT = {
    "EventId": 22795, "EventBodyName": "Committee on Technology", "EventDate": "2026-10-16T00:00:00",
    "EventTime": "10:00 AM", "EventLocation": "Council Chambers - City Hall", "EventAgendaStatusName": "Final",
    "EventMinutesStatusName": "Draft",
    "EventAgendaFile": "https://nyc.legistar1.com/nyc/meetings/2026/10/22795_A_Committee_on_Technology_26-10-16_Committee_Agenda.pdf",
    "EventAgendaLastPublishedUTC": "2026-10-13T20:25:46.037", "EventMinutesFile": None,
    "EventVideoPath": "https://councilnyc.viebit.com/vod/?s=true&v=NYCC-PV-CH-CHA_261016-101016.mp4",
    "EventInSiteURL": "https://nyc.legistar.com/MeetingDetail.aspx?LEGID=22795",
    "EventItems": [{"EventItemAgendaSequence": 1, "EventItemMatterId": 79637, "EventItemMatterFile": "T2026-2684",
                    "EventItemMatterName": "Oversight - Continuing Discussion about the Risks Posed by Artificial Intelligence.",
                    "EventItemMatterType": "Oversight", "EventItemMatterStatus": "Committee"},
                   {"EventItemAgendaSequence": 2, "EventItemMatterId": None, "EventItemTitle": "Procedural line"}],
}
MATTERS = {79637: {"MatterId": 79637, "MatterFile": "T2026-2684",
                   "MatterName": "Oversight - Continuing Discussion about the Risks Posed by Artificial Intelligence."}}


def att(i, name, url, sort=0):
    return {"MatterAttachmentId": i, "MatterAttachmentName": name, "MatterAttachmentHyperlink": url,
            "MatterAttachmentLastModifiedUtc": "2026-10-15T15:39:11.387", "MatterAttachmentSort": sort}


class LegistarHelpers(unittest.TestCase):
    def test_slug_and_filename_match_2026_10_05_rule(self):
        # Rows from hearings/2026-10-05-committee-of-the-whole-ai/legistar/manifest.csv
        self.assertEqual(fl.attachment_filename("Int 0161-2026", "Fiscal Impact Statement - City Council",
                                                "https://nyc.legistar1.com/nyc/attachments/819e.docx"),
                         "int-0161-2026-fiscal-impact-statement-city-council.docx")
        self.assertEqual(fl.attachment_filename("T2026-2573", "Exhibit 1", "https://nyc.legistar1.com/nyc/attachments/4661.PDF"),
                         "t2026-2573-exhibit-1.pdf")
        self.assertEqual(fl.attachment_filename("T2026-2599", "Int. No.", "https://x/a.docx"), "t2026-2599-int-no.docx")

    def test_short_utc(self):
        self.assertEqual(fl.short_utc("2026-10-15T15:39:11.387"), "2026-10-15 15:39")
        self.assertEqual(fl.short_utc(None), "")

    def test_download_refuses_a_redirect_off_legistar(self):
        class Resp(io.BytesIO):
            def geturl(self):
                return "https://example.org/elsewhere.pdf"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fl.urllib.request, "urlopen", lambda req, timeout: Resp(b"x")):
            with self.assertRaises(ValueError):
                fl.download("https://nyc.legistar1.com/nyc/attachments/a.pdf", Path(d) / "a.pdf")
            self.assertFalse((Path(d) / "a.pdf").exists())

    def test_only_legistar_https_files_are_downloadable(self):
        self.assertTrue(fl.is_legistar_file("https://nyc.legistar1.com/nyc/attachments/a.pdf"))
        self.assertFalse(fl.is_legistar_file("http://nyc.legistar1.com/nyc/attachments/a.pdf"))
        self.assertFalse(fl.is_legistar_file("https://example.org/a.pdf"))
        self.assertFalse(fl.is_legistar_file(None))

    def test_plan_orders_agenda_first_dedupes_and_skips_external_links(self):
        atts = {79637: [att(2, "Exhibit 1", "https://nyc.legistar1.com/nyc/attachments/b.pdf", 2),
                        att(1, "Committee Report", "https://nyc.legistar1.com/nyc/attachments/156e.docx", 1),
                        att(3, "Exhibit 1", "https://nyc.legistar1.com/nyc/attachments/c.pdf", 3),
                        att(4, "Press release", "https://example.org/x.html", 4)]}
        rows, skipped = fl.plan_files(EVENT, MATTERS, atts)
        self.assertEqual([r["filename"] for r in rows],
                         ["meeting-agenda.pdf", "t2026-2684-committee-report.docx",
                          "t2026-2684-exhibit-1.pdf", "t2026-2684-exhibit-1-2.pdf"])
        self.assertEqual(rows[0]["matter_file"], "Meeting")
        self.assertEqual(rows[0]["matter_title"], "Meeting agenda, Legistar event 22795")
        self.assertEqual(rows[0]["last_modified_utc"], "2026-10-13 20:25")
        self.assertEqual([s["attachment_name"] for s in skipped], ["Press release"])

    def test_manifest_columns_equal_the_published_manifest(self):
        published = REPO / "hearings" / "2026-10-05-committee-of-the-whole-ai" / "legistar" / "manifest.csv"
        header = published.read_text(encoding="utf-8").splitlines()[0]
        rows, _ = fl.plan_files(EVENT, MATTERS, {79637: [att(1, "Committee Report", "https://nyc.legistar1.com/a.docx")]})
        for r in rows:
            r["bytes"] = 10
        text = fl.manifest_csv(rows)
        self.assertEqual(text.splitlines()[0], header)
        parsed = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(parsed[1]["filename"], "t2026-2684-committee-report.docx")
        self.assertEqual(parsed[1]["bytes"], "10")

    def test_readme_names_event_video_and_files(self):
        rows, _ = fl.plan_files(EVENT, MATTERS, {})
        text = fl.readme_text(EVENT, MATTERS, rows, [], "2026-10-19T10:35:59Z")
        self.assertIn("| Legistar event | 22795 |", text)
        self.assertIn("NYCC-PV-CH-CHA_261016-101016.mp4", text)
        self.assertIn("`meeting-agenda.pdf`", text)

    def test_readme_file_rows_parse_with_build_hearing(self):
        import build_hearing as bh
        rows, _ = fl.plan_files(EVENT, MATTERS, {79637: [att(1, "Committee Report", "https://nyc.legistar1.com/a.docx")]})
        for r in rows:
            r["bytes"] = 1
        text = fl.readme_text(EVENT, MATTERS, rows, [], "2026-10-19T10:35:59Z")
        parsed = [m.groups() for m in map(bh.README_ROW.match, text.splitlines()) if m]
        self.assertEqual(parsed, [
            ("Meeting", "Agenda", EVENT["EventAgendaFile"], "2026-10-13 20:25", "meeting-agenda.pdf"),
            ("T2026-2684", "Committee Report", "https://nyc.legistar1.com/a.docx", "2026-10-15 15:39",
             "t2026-2684-committee-report.docx")])


class LegistarIntoBuild(unittest.TestCase):
    """fetch_legistar.py's folder (manifest.csv + files), pre- and post-hearing, read by
    build_hearing.build_legistar end to end: the post-hearing copy of a file wins."""

    META = {"bills": [], "oversight_topic": {"file": "T2026-2684", "name": "Oversight - Topic"},
            "legistar": {"event_id": 22795}}

    def write_fetch(self, folder: Path, atts: list[dict], payloads: dict[str, bytes]) -> None:
        folder.mkdir(parents=True)
        rows, _ = fl.plan_files(EVENT, MATTERS, {79637: atts})
        for r in rows:
            (folder / r["filename"]).write_bytes(payloads.get(r["filename"], b"agenda"))
            r["bytes"] = (folder / r["filename"]).stat().st_size
        (folder / "manifest.csv").write_text(fl.manifest_csv(rows), encoding="utf-8")

    def test_pre_and_post_fetch_folders_build(self):
        import build_hearing as bh
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            report = att(1, "Committee Report", "https://nyc.legistar1.com/nyc/attachments/156e.docx")
            self.write_fetch(d / "pre", [report], {"t2026-2684-committee-report.docx": b"draft"})
            later = {**report, "MatterAttachmentLastModifiedUtc": "2026-10-18T09:00:00"}
            testimony = att(2, "Hearing Testimony", "https://nyc.legistar1.com/nyc/attachments/9f.pdf", 2)
            self.write_fetch(d / "post", [later, testimony],
                             {"t2026-2684-committee-report.docx": b"final version",
                              "t2026-2684-hearing-testimony.pdf": b"%PDF testimony"})
            manifest = bh.build_legistar(self.META, d / "out", None, d / "pre", None, d / "post")
            got = {m["filename"]: m for m in manifest}
            self.assertEqual(set(got), {"meeting-agenda.pdf", "t2026-2684-committee-report.docx",
                                        "t2026-2684-hearing-testimony.pdf"})
            self.assertEqual((d / "out" / "legistar" / "t2026-2684-committee-report.docx").read_bytes(), b"final version")
            self.assertEqual(got["t2026-2684-committee-report.docx"]["last_modified_utc"], "2026-10-18 09:00")
            self.assertEqual(got["t2026-2684-committee-report.docx"]["bytes"], len(b"final version"))
            on_disk = list(csv.DictReader(io.StringIO((d / "out" / "legistar" / "manifest.csv").read_text(encoding="utf-8"))))
            self.assertEqual(len(on_disk), 3)

    def test_size_mismatch_stops_the_build(self):
        import build_hearing as bh
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.write_fetch(d / "pre", [], {})
            (d / "pre" / "meeting-agenda.pdf").write_bytes(b"changed after download")
            with self.assertRaises(SystemExit):
                bh.build_legistar(self.META, d / "out", None, d / "pre", None, None)


PAGE = """<html><head><title>x</title></head><body>
<script>
  var pageConfig = {"video":{"id":"5vNSMDW7rAw8xHkH","title":"NYCC-PV-CH-CHA_261016-101016.mp4","dateCreated":1792167007,
  "src":[{"storage":"https://vbfast-vod.viebit.com/otfp/counciln/5vNSMDW7rAw8xHkH/","url":"NYCC-PV-CH-CHA_261016-101016,master.m3u8?fmp4=1","type":"application/x-mpegurl"}],
  "textTracks":[{"kind":"captions","srclang":"en","label":"English","src":"https://vbfast-vod.viebit.com/counciln/5vNSMDW7rAw8xHkH/NYCC-PV-CH-CHA_261016-101016.vtt"}]},
  "downloadEnabled":true,"hasAccess":true};
</script></body></html>"""


class MediaHelpers(unittest.TestCase):
    def test_page_config_to_urls(self):
        urls = fm.media_urls(fm.parse_page_config(PAGE))
        self.assertEqual(urls["filename"], "NYCC-PV-CH-CHA_261016-101016.mp4")
        self.assertEqual(urls["viebit_id"], "5vNSMDW7rAw8xHkH")
        self.assertEqual(urls["mp4_url"], "https://vbfast-vod.viebit.com/counciln/5vNSMDW7rAw8xHkH/NYCC-PV-CH-CHA_261016-101016.mp4")
        self.assertTrue(urls["vtt_url"].endswith("/NYCC-PV-CH-CHA_261016-101016.vtt"))
        self.assertEqual(urls["hls_url"], "https://vbfast-vod.viebit.com/otfp/counciln/5vNSMDW7rAw8xHkH/"
                                          "NYCC-PV-CH-CHA_261016-101016,master.m3u8?fmp4=1")

    def test_page_without_config_fails(self):
        with self.assertRaises(ValueError):
            fm.parse_page_config("<html>Cannot load the VieBit video player.</html>")

    def test_unexpected_title_fails(self):
        cfg = fm.parse_page_config(PAGE.replace("NYCC-PV-CH-CHA_261016-101016.mp4", "something.mov"))
        with self.assertRaises(ValueError):
            fm.media_urls(cfg)

    def test_captions_from_another_video_folder_fail(self):
        cfg = fm.parse_page_config(PAGE.replace("/counciln/5vNSMDW7rAw8xHkH/NYCC-PV-CH-CHA_261016-101016.vtt",
                                                "/counciln/OTHER/NYCC-PV-CH-CHA_261016-101016.vtt"))
        with self.assertRaises(ValueError):
            fm.media_urls(cfg)

    def test_no_captions_means_no_derived_mp4(self):
        cfg = fm.parse_page_config(PAGE)
        cfg["video"]["textTracks"] = []
        self.assertIsNone(fm.media_urls(cfg)["mp4_url"])

    def test_hosts_outside_viebit_are_refused(self):
        with self.assertRaises(SystemExit):
            fm.check_host("https://example.org/video.mp4")

    def test_audio_commands_match_published_formats(self):
        cmds = dict((p.name, c) for p, c in fm.audio_commands(Path("/v/in.mp4"), Path("/out")))
        mp3 = cmds["hearing-audio-64k.mp3"]
        self.assertEqual(mp3[mp3.index("-ac") + 1], "1")
        self.assertEqual(mp3[mp3.index("-ar") + 1], "16000")
        self.assertEqual(mp3[mp3.index("-b:a") + 1], "64k")
        opus = cmds["hearing-audio-16k.opus"]
        self.assertEqual(opus[opus.index("-c:a") + 1], "libopus")
        self.assertEqual(opus[opus.index("-b:a") + 1], "16k")
        self.assertIn("-vn", opus)

    def test_hms(self):
        self.assertEqual(fm.hms(7048.533), "1:57:28")

    def test_partial_path_keeps_the_extension_ffmpeg_needs(self):
        self.assertEqual(fm.partial_path(Path("/m/hearing-audio-16k.opus")).name, "hearing-audio-16k.partial.opus")

    def test_audio_staleness(self):
        with tempfile.TemporaryDirectory() as d:
            video, audio = Path(d) / "v.mp4", Path(d) / "a.mp3"
            video.write_bytes(b"v")
            self.assertTrue(fm.audio_is_stale(audio, video), "missing audio")
            audio.write_bytes(b"a")
            os.utime(video, (1000, 1000))
            os.utime(audio, (2000, 2000))
            self.assertFalse(fm.audio_is_stale(audio, video))
            self.assertTrue(fm.audio_is_stale(audio, video, video_refetched=True), "video fetched again")
            os.utime(video, (3000, 3000))
            self.assertTrue(fm.audio_is_stale(audio, video), "video newer than audio")

    def test_make_audio_renames_only_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "hearing-audio-64k.mp3"
            dest.write_bytes(b"old good audio")

            def ffmpeg_fails(cmd, check):
                Path(cmd[-1]).write_bytes(b"trunc")
                raise fm.subprocess.CalledProcessError(1, cmd)

            with mock.patch.object(fm.subprocess, "run", ffmpeg_fails):
                with self.assertRaises(fm.subprocess.CalledProcessError):
                    fm.make_audio(["ffmpeg", "-i", "v.mp4", str(dest)], dest)
            self.assertEqual(dest.read_bytes(), b"old good audio", "a failed run must not replace the file")

            def ffmpeg_ok(cmd, check):
                self.assertEqual(Path(cmd[-1]).name, "hearing-audio-64k.partial.mp3")
                Path(cmd[-1]).write_bytes(b"new audio")

            with mock.patch.object(fm.subprocess, "run", ffmpeg_ok):
                fm.make_audio(["ffmpeg", "-i", "v.mp4", str(dest)], dest)
            self.assertEqual(dest.read_bytes(), b"new audio")
            self.assertFalse(fm.partial_path(dest).exists())


SEGS = [
    {"start": 10.2, "end": 12.0, "speaker": 0, "text": "Good morning.", "words": []},
    {"start": 12.5, "end": 14.0, "speaker": 0, "text": "Ready.", "words": []},
    {"start": 14.1, "end": 20.0, "speaker": 1, "text": "Thank you.", "words": []},
    {"start": 26.0, "end": 27.0, "speaker": 1, "text": "After a pause.", "words": []},
]


class RenderRaw(unittest.TestCase):
    def test_render_merges_same_cluster_under_5s(self):
        self.assertEqual(rd.render(SEGS),
                         "[00:00:10] Speaker 0: Good morning. Ready.\n\n"
                         "[00:00:14] Speaker 1: Thank you.\n\n"
                         "[00:00:26] Speaker 1: After a pause.\n\n")

    def test_summary_counts(self):
        s = rd.summary(SEGS)
        self.assertEqual((s["segments"], s["turns"], s["speaker_clusters"]), (4, 3, 2))
        self.assertEqual(s["turns_per_cluster"], {0: 1, 1: 2})

    def test_hms_rolls_over_hours(self):
        self.assertEqual(rd.hms(36492.48), "10:08:12")


if __name__ == "__main__":
    unittest.main()
