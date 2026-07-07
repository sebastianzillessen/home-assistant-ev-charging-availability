"""Live test: download the real SFOE feeds and parse them.

This test hits the public ``data.geo.admin.ch`` endpoints, so it is opt-in: it
only runs when ``RUN_LIVE_TESTS=1`` is set (e.g. the dedicated CI workflow). It
is the real-world guard that our OICP parser keeps working against the actual
file shapes, which use the single-object-vs-array convention.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import socket
import urllib.request

import aiohttp
import pytest
import pytest_socket

from custom_components.swiss_ev_charging.api import (
    parse_evse_data,
    parse_evse_status,
)
from custom_components.swiss_ev_charging.const import (
    AVAILABILITY_STATES,
    EVSE_DATA_URL,
    EVSE_STATUS_URL,
    STATE_UNKNOWN,
)
from custom_components.swiss_ev_charging.ecarup import async_resolve_ecarup_states
from custom_components.swiss_ev_charging.move import async_resolve_move_states

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="live network test; set RUN_LIVE_TESTS=1 to enable",
)


@pytest.fixture(autouse=True)
def _allow_live_sockets():
    """Re-enable real network sockets for these opt-in live tests.

    ``pytest-homeassistant-custom-component`` blocks sockets before every test:
    it both disables ``socket.socket`` and restricts ``connect()`` to
    ``127.0.0.1``. These tests intentionally hit public endpoints, so lift both
    restrictions (``enable_socket()`` alone does not clear the host allowlist).
    """
    _lift_socket_restrictions()
    yield


def _lift_socket_restrictions() -> None:
    """Fully restore real sockets, including the connect() host allowlist."""
    pytest_socket.enable_socket()
    # enable_socket() restores socket.socket but not the connect() host guard.
    socket.socket.connect = pytest_socket._true_connect


def _download(url: str) -> dict:
    """Download and decode a JSON document from the public endpoint.

    The CDN serves these files gzip-compressed; urllib does not auto-decompress
    (the integration itself uses aiohttp, which does), so handle it here.
    """
    _lift_socket_restrictions()
    request = urllib.request.Request(url, headers={"User-Agent": "ha-swiss-ev-tests"})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        raw = response.read()
    if response.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


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


def test_live_ecarup_fallback_resolves_states() -> None:
    """The eCarUp public API resolves live states the SFOE feed leaves unknown.

    Uses two real eCarUp EVSEs near Zürich that the SFOE feed reports as
    ``Unknown``. Their live state varies over time, so we only assert the
    resolver runs cleanly against the real endpoints and never emits an invalid
    or ``unknown`` state - not a specific availability.
    """
    targets = [
        ("CH*ECUEDR654CLPY9WN3HBTTGEYKFKTVS", 47.380003, 8.552967),
        ("CH*ECUEHTXBFZXT3VVJEJF2YMK8YX29TW", 47.38002, 8.552946),
    ]

    async def _run() -> dict[str, str]:
        async with aiohttp.ClientSession() as session:
            return await async_resolve_ecarup_states(session, targets)

    resolved = asyncio.run(_run())

    # Every resolved value is a concrete, valid availability state.
    for evse_id, state in resolved.items():
        assert evse_id in {t[0] for t in targets}
        assert state in AVAILABILITY_STATES
        assert state != STATE_UNKNOWN


def test_live_move_fallback_resolves_states() -> None:
    """The Move public API resolves live states the SFOE feed leaves unknown.

    Covers Move's own points and the roaming networks the same endpoint reports
    (AVIA VOLT, Power Up, Repower / PLUG N ROLL). Each is queried on its own
    (they are far apart), and since live state varies we only assert the resolver
    runs cleanly and returns concrete, valid states joined by the exact EvseID.
    """
    targets = [
        ("CH*CCI*E22078", 46.23432, 6.055602),  # Move, SIG CERN Meyrin
        ("CH*AVI*E10141", 47.408282, 9.303683),  # AVIA VOLT Shopping Arena
        ("CH*POW*E92255", 46.561268, 7.375258),  # Power Up LANDI Zweisimmen
        ("CH*REPE020*01*1", 46.45931, 9.795548),  # Repower / PLUG N ROLL
    ]

    async def _resolve_one(target) -> dict[str, str]:
        async with aiohttp.ClientSession() as session:
            return await async_resolve_move_states(session, [target])

    for target in targets:
        resolved = asyncio.run(_resolve_one(target))
        for evse_id, state in resolved.items():
            assert evse_id == target[0]
            assert state in AVAILABILITY_STATES
            assert state != STATE_UNKNOWN
