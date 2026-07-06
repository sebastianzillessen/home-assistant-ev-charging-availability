"""Live test: download the real SFOE feeds and parse them.

This test hits the public ``data.geo.admin.ch`` endpoints, so it is opt-in: it
only runs when ``RUN_LIVE_TESTS=1`` is set (e.g. the dedicated CI workflow). It
is the real-world guard that our OICP parser keeps working against the actual
file shapes, which use the single-object-vs-array convention.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from custom_components.swiss_ev_charging.api import (
    parse_evse_data,
    parse_evse_status,
)
from custom_components.swiss_ev_charging.const import EVSE_DATA_URL, EVSE_STATUS_URL

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="live network test; set RUN_LIVE_TESTS=1 to enable",
)


def _download(url: str) -> dict:
    """Download and decode a JSON document from the public endpoint."""
    request = urllib.request.Request(url, headers={"User-Agent": "ha-swiss-ev-tests"})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.load(response)


@pytest.fixture(scope="module")
def live_master() -> dict:
    """Download the (large) EVSEData master file once for the module."""
    return _download(EVSE_DATA_URL)


@pytest.fixture(scope="module")
def live_status() -> dict:
    """Download the EVSEStatus live file once for the module."""
    return _download(EVSE_STATUS_URL)


def test_live_evse_data_parses(live_master: dict) -> None:
    """The real EVSEData file parses into many charging points without error."""
    points = parse_evse_data(live_master)
    assert len(points) > 1000, f"expected a country-wide file, got {len(points)}"

    # A meaningful share of points should have coordinates and an ID.
    with_coords = [p for p in points.values() if p.latitude is not None]
    assert len(with_coords) > 100
    assert all(p.evse_id for p in points.values())


def test_live_evse_status_parses(live_status: dict) -> None:
    """The real EVSEStatus file parses into many availability states."""
    statuses = parse_evse_status(live_status)
    assert len(statuses) > 1000
    # Every value must be one of our normalised states.
    from custom_components.swiss_ev_charging.const import AVAILABILITY_STATES

    assert set(statuses.values()) <= set(AVAILABILITY_STATES)


def test_live_data_and_status_share_ids(live_master: dict, live_status: dict) -> None:
    """The two files join on EvseID, so they must share a large key overlap."""
    points = parse_evse_data(live_master)
    statuses = parse_evse_status(live_status)
    overlap = set(points) & set(statuses)
    assert len(overlap) > 1000, f"expected large EvseID overlap, got {len(overlap)}"
