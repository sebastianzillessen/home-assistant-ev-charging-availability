#!/usr/bin/env python3
"""Generate JSON Schemas from the live SFOE / ich-tanke-strom OICP feeds.

Downloads the two public endpoints (or reads local files with ``--input-dir``)
and infers a JSON Schema for each using ``genson``, writing deterministic output
to ``schemas/``. A change in the emitted schema between runs signals that the
upstream feed structure changed (new field, changed type, different casing) —
which is the class of change that can silently break the parser in
``custom_components/swiss_ev_charging/api.py``.

Usage:
    python scripts/generate_evse_schema.py                 # download live feeds
    python scripts/generate_evse_schema.py --input-dir DIR # read evse_data.json / evse_status.json
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from genson import SchemaBuilder

# Keep in sync with custom_components/swiss_ev_charging/const.py.
FEEDS = {
    "evse_data": (
        "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet"
        "/data/oicp/ch.bfe.ladestellen-elektromobilitaet.json"
    ),
    "evse_status": (
        "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet"
        "/status/oicp/ch.bfe.ladestellen-elektromobilitaet.json"
    ),
}

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _download(url: str) -> dict:
    """Download and decode a JSON document from the public endpoint."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "ha-swiss-ev-schema-gen"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.load(response)


def build_schema(data: object) -> dict:
    """Infer a deterministic JSON Schema for a decoded feed document."""
    builder = SchemaBuilder()
    builder.add_schema({"$schema": "http://json-schema.org/draft-07/schema#"})
    builder.add_object(data)
    return builder.to_schema()


def render(schema: dict) -> str:
    """Serialise a schema stably so diffs reflect real structural changes."""
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    """Generate a schema file for each feed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Read <name>.json from this directory instead of downloading.",
    )
    args = parser.parse_args()

    SCHEMA_DIR.mkdir(exist_ok=True)
    for name, url in FEEDS.items():
        if args.input_dir is not None:
            data = json.loads(
                (args.input_dir / f"{name}.json").read_text(encoding="utf-8")
            )
        else:
            data = _download(url)
        out_path = SCHEMA_DIR / f"{name}.schema.json"
        out_path.write_text(render(build_schema(data)), encoding="utf-8")
        print(f"wrote {out_path.relative_to(SCHEMA_DIR.parent)}")


if __name__ == "__main__":
    main()
