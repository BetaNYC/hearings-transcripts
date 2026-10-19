#!/usr/bin/env python3
"""Validate a clean-verbatim transcript against the unedited one (stage 5).

Python 3.11 to 3.14, standard library only. No network access.

    python3 scripts/validate_clean.py UNEDITED CLEAN [--names]

Checks: same turn count; byte-identical `[HH:MM:SS] Name:` prefixes; overall length ratio;
turns that shrank by more than 40%; how many turns changed. With --names, lists every
capitalized token (proper-noun candidate) added or removed, with counts and where, so a
reviewer can check each changed name. Header lines before the first `[` turn are ignored in
both files. Exit 0 only if the turn count and every prefix match: build_hearing.py refuses
the same mismatches, so run this first.

First written for the 2026-10-05 hearing and used again for 2026-10-16. Turns are split with
build_hearing.py's own splitter, so the validator and the build always see the same turns.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_hearing import parse_transcript_text  # noqa: E402  (the build's own turn splitter)

SEP = ": "  # the build requires "Name: text"; a turn without it is reported as a mismatch


def turns_of(text: str) -> list[str]:
    """Each turn as one string, `[HH:MM:SS] rest`, split exactly as build_hearing.py splits."""
    return [f"[{h}] {rest}" for h, rest in parse_transcript_text(text)]


def turns(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return turns_of(f.read())


def pre(x: str) -> str:
    """`[HH:MM:SS] Name:`; a turn with no `Name: ` separator returns a marker that never matches."""
    head, sep, _ = x.partition(SEP)
    return head + ":" if sep else "<no 'Name: ' separator> " + x[:40]


def body(x: str) -> str:
    return x.partition(SEP)[2]


def caps(s: str) -> collections.Counter:
    """Capitalized tokens not at a sentence start, plus all-caps acronyms."""
    out: collections.Counter = collections.Counter()
    s = re.sub(r"\b(Mr|Ms|Mrs|Dr)\. ", r"\1 ", s)  # honorifics are not sentence ends
    for m in re.finditer(r"(?<![.?!:]\s)(?<!^)\b([A-Z][\w'’\-é]*)", s.strip()):
        out[m.group(1)] += 1
    return out


def compare(a: list[str], b: list[str]) -> dict:
    bad = [i for i, (x, y) in enumerate(zip(a, b)) if pre(x) != pre(y)]
    return {
        "ok": len(a) == len(b) and not bad,
        "turns_in": len(a), "turns_out": len(b), "mismatches": bad,
        "ratio": sum(len(x) for x in b) / max(1, sum(len(x) for x in a)),
        "short": [pre(x) for x, y in zip(a, b) if len(y) < 0.6 * len(x) and len(x) > 200],
        "changed": sum(1 for x, y in zip(a, b) if x != y),
    }


def name_changes(a: list[str], b: list[str]) -> tuple[collections.Counter, collections.Counter, dict]:
    added, removed = collections.Counter(), collections.Counter()
    where = collections.defaultdict(list)
    for x, y in zip(a, b):
        ca, cb = caps(body(x)), caps(body(y))
        for k, v in (cb - ca).items():
            added[k] += v
            where["+" + k].append(pre(x)[1:9])
        for k, v in (ca - cb).items():
            removed[k] += v
            where["-" + k].append(pre(x)[1:9])
    return added, removed, where


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a clean-verbatim transcript against the unedited one.",
                                 allow_abbrev=False)
    ap.add_argument("unedited")
    ap.add_argument("clean")
    ap.add_argument("--names", action="store_true", help="list capitalized tokens added or removed")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on unknown flags or missing paths
        return int(e.code or 0)
    try:
        a, b = turns(args.unedited), turns(args.clean)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    r = compare(a, b)
    print(f"turns in={r['turns_in']} out={r['turns_out']} prefix_mismatch={len(r['mismatches'])} "
          f"changed={r['changed']} length_ratio={r['ratio']:.2f} big_shrinks={len(r['short'])}")
    if r["mismatches"]:
        print("first mismatches", [(pre(a[i]), pre(b[i])) for i in r["mismatches"][:5]])
    if r["short"]:
        print("shrunk >40%:", r["short"][:10])
    if args.names:
        added, removed, where = name_changes(a, b)
        print("ADDED capitalized tokens:")
        for k, v in sorted(added.items(), key=lambda kv: -kv[1]):
            print(f"  +{k} x{v}  {where['+' + k][:4]}")
        print("REMOVED capitalized tokens:")
        for k, v in sorted(removed.items(), key=lambda kv: -kv[1]):
            print(f"  -{k} x{v}  {where['-' + k][:4]}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
