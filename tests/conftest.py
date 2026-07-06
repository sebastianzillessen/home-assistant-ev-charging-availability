"""Shared fixtures for the Swiss EV Charging tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    yield


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from the fixtures directory."""
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def evse_data() -> dict:
    """Return the parsed EVSEData fixture payload."""
    return load_fixture("evse_data.json")


@pytest.fixture
def evse_status() -> dict:
    """Return the parsed EVSEStatus fixture payload."""
    return load_fixture("evse_status.json")
