"""Tests for the JSON schema generator (scripts/generate_evse_schema.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .conftest import load_fixture

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "generate_evse_schema.py"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_evse_schema", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_schema_captures_data_shape() -> None:
    """The generated schema reflects the real feed structure (lowercase power)."""
    gen = _load_generator()
    schema = gen.build_schema(load_fixture("evse_data_real.json"))

    record = schema["properties"]["EVSEData"]["items"]["properties"][
        "EVSEDataRecord"
    ]["items"]["properties"]
    facility = record["ChargingFacilities"]["items"]["properties"]

    # The feed exposes power/powertype as lowercase string fields.
    assert facility["power"]["type"] == "string"
    assert facility["powertype"]["type"] == "string"
    assert record["EvseID"]["type"] == "string"


def test_render_is_deterministic() -> None:
    """Rendering the same data twice yields byte-identical output (stable diffs)."""
    gen = _load_generator()
    data = load_fixture("evse_status_real.json")
    assert gen.render(gen.build_schema(data)) == gen.render(gen.build_schema(data))
