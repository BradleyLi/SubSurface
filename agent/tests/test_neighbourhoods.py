"""Tests for Toronto neighbourhood loading and resolution."""

from __future__ import annotations

import re

from agent.neighbourhoods import (
    centroid_for_name,
    load_neighbourhoods,
    neighbourhood_names,
    resolve_neighbourhood,
)


def test_load_neighbourhoods_count_and_bounds():
    nbs = load_neighbourhoods()
    assert len(nbs) == 140
    # All centroids should sit inside the Toronto bounding box.
    for nb in nbs:
        assert 43.5 <= nb.lat <= 43.9
        assert -79.7 <= nb.lon <= -79.1
    # The trailing " (123)" area-code suffix is stripped from the display name
    # (descriptive parentheticals like "Mimico (includes ...)" are preserved).
    assert all(not re.search(r"\(\d+\)\s*$", nb.name) for nb in nbs)


def test_centroid_for_name_roundtrip():
    name = load_neighbourhoods()[0].name
    coords = centroid_for_name(name)
    assert coords is not None
    lat, lon = coords
    assert 43.5 <= lat <= 43.9
    assert -79.7 <= lon <= -79.1


def test_fuzzy_resolves_known_area():
    match = resolve_neighbourhood("water main break in The Annex", use_llm=False)
    assert match is not None
    assert match.name == "Annex"
    assert match.method == "fuzzy"
    assert match.confidence >= 0.62


def test_fuzzy_rejects_unrelated_text():
    assert resolve_neighbourhood("unrelated chatter about pizza", use_llm=False) is None
    assert resolve_neighbourhood("", use_llm=False) is None


def test_neighbourhood_names_are_unique_nonempty():
    names = neighbourhood_names()
    assert len(names) == 140
    assert all(n.strip() for n in names)
