#!/usr/bin/env python3
"""Render a Deepgram intermediate file as the raw, unnamed transcript text.

Python 3.11 to 3.14, standard library only. No network access.

    python3 scripts/render_deepgram_raw.py <dir>/deepgram-intermediate.json <dir>/<slug>-transcript-deepgram-raw.txt

Input is `deepgram-intermediate.json` ({segments:[{start,end,speaker,text,words}]}). Segments
are merged into turns with `merge_turns()` from build_hearing.py (same voice cluster, gap under
5 seconds), so the turn count here equals the count the build checks speaker labels against.
Each turn is written as `[HH:MM:SS] Speaker <cluster>: <text>` followed by a blank line, the
format of `2026-10-05-committee-of-the-whole-transcript-deepgram-raw.txt`. This file is the
starting point for speaker naming, which replaces `Speaker <cluster>` with names.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_hearing import merge_turns  # noqa: E402


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def render(segments: list[dict]) -> str:
    out = []
    for t in merge_turns(segments):
        text = " ".join(s["text"] for s in t["segments"])
        out.append(f"[{hms(t['start'])}] Speaker {t['cluster']}: {text}\n\n")
    return "".join(out)


def summary(segments: list[dict]) -> dict:
    turns = merge_turns(segments)
    return {"segments": len(segments), "turns": len(turns),
            "speaker_clusters": len({s["speaker"] for s in segments}),
            "turns_per_cluster": dict(sorted(Counter(t["cluster"] for t in turns).items()))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("intermediate", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    d = json.loads(a.intermediate.read_text(encoding="utf-8"))
    segs = d["segments"]
    a.out.write_text(render(segs), encoding="utf-8")
    print(json.dumps({"out": str(a.out), "duration_sec": d.get("duration_sec"), **summary(segs)}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
