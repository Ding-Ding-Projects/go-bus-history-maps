#!/usr/bin/env python3
"""Download the explicit public source feeds; verify saved snapshot checksums.

The publisher's live URL will change. The 2026 archive hash must not silently
change: use an archived original or import a separately dated newer snapshot.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT / ".cache" / "feeds")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    expected = {r["id"]: r["sha256"] for r in json.loads((ROOT / "data/snapshots.json").read_text())}
    for spec in json.loads((ROOT / "data/feed-manifest.json").read_text()):
        destination = args.directory / spec["filename"]
        data = destination.read_bytes() if destination.exists() else urlopen(spec["url"], timeout=120).read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected[spec["id"]]:
            raise SystemExit(f"{spec['id']}: source checksum changed. Refusing to relabel new data as an old snapshot. Expected {expected[spec['id']]}, got {digest}. Obtain the matching archived feed or add a new manifest entry with its true date.")
        destination.write_bytes(data)
        print(f"Verified {spec['id']}: {len(data):,} bytes")


if __name__ == "__main__":
    main()
