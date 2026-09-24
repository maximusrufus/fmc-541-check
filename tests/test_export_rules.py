"""Guard rails for the rules/fmc-541.json cross-language export.

Same drift-guard pattern as test_real_corpus.py's engine-pin: the committed
JSON must equal a fresh call to export(), and every quoted string in it must
be identical to the object rules.py itself defines -- never a retyped copy.
"""

from __future__ import annotations

import json
from pathlib import Path

from demurragedesk.export_rules import export
from demurragedesk.rules import CLOCKS, FACTORS_545_5, REQUIRED_ELEMENTS, RULE_541_5

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORTED_JSON = REPO_ROOT / "rules" / "fmc-541.json"


def test_committed_json_exists():
    assert EXPORTED_JSON.exists(), (
        "run: python -m demurragedesk.export_rules --out rules/fmc-541.json"
    )


def test_committed_json_matches_fresh_export():
    """The committed file must not silently drift from rules.py."""
    committed = json.loads(EXPORTED_JSON.read_text(encoding="utf-8"))
    fresh = export()
    assert committed == fresh, (
        "rules/fmc-541.json is stale -- regenerate with "
        "`python -m demurragedesk.export_rules --out rules/fmc-541.json`"
    )


def test_export_is_json_serializable_and_reloads_identically():
    doc = export()
    reloaded = json.loads(json.dumps(doc))
    assert reloaded == doc


def test_top_level_shape():
    doc = export()
    for key in (
        "schema_version",
        "generated_from",
        "elements",
        "clocks",
        "consequences",
        "factors_545_5",
        "vacated",
        "provenance",
    ):
        assert key in doc, key
    assert isinstance(doc["schema_version"], int)
    assert isinstance(doc["elements"], list)
    assert isinstance(doc["clocks"], list)
    assert isinstance(doc["consequences"], list)
    assert isinstance(doc["factors_545_5"], list)
    assert isinstance(doc["vacated"], list)
    gf = doc["generated_from"]
    for key in ("package_version", "retrieved", "sources"):
        assert key in gf, key


def test_vacated_contains_exactly_the_two_reserved_sections():
    doc = export()
    assert set(doc["vacated"]) == {"46 CFR 541.4", "46 CFR 502.303"}


def test_element_count_and_text_matches_source_object():
    doc = export()
    assert len(doc["elements"]) == len(REQUIRED_ELEMENTS) == 20
    by_key = {e.key: e for e in REQUIRED_ELEMENTS}
    for entry in doc["elements"]:
        src = by_key[entry["key"]]
        assert entry["text"] == src.text
        assert entry["group"] == src.group
        assert entry["verified"] == src.verified
        assert tuple(entry["applies_to"]) == src.applies_to
        assert entry["field"] == src.field_name


def test_clock_count_and_text_matches_source_object():
    doc = export()
    assert len(doc["clocks"]) == len(CLOCKS) == 6
    by_cite = {c.cite: c for c in CLOCKS.values()}
    for entry in doc["clocks"]:
        src = by_cite[entry["cite"]]
        assert entry["text"] == src.text
        assert entry["days"] == src.days
        assert entry["day_type"] == "calendar"
        assert entry["trigger"] == src.anchor
        assert entry["verified"] == src.verified


def test_consequence_text_matches_541_5():
    doc = export()
    assert len(doc["consequences"]) == 1
    entry = doc["consequences"][0]
    assert entry["cite"] == RULE_541_5["cite"]
    assert entry["text"] == RULE_541_5["text"]
    assert entry["heading"] == RULE_541_5["heading"]
    assert entry["verified"] == RULE_541_5["verified"]


def test_factors_545_5_text_matches_source_object():
    doc = export()
    assert len(doc["factors_545_5"]) == len(FACTORS_545_5) == 6
    for entry, src in zip(doc["factors_545_5"], FACTORS_545_5):
        assert entry["key"] == src.key
        assert entry["label"] == src.label
        assert entry["text"] == src.text
        assert entry["fact_field"] == src.fact_field
        assert entry["evidence"] == src.evidence
        assert entry["enumerated"] == src.enumerated
        assert entry["verified"] == src.verified

    enumerated = [f for f in doc["factors_545_5"] if f["enumerated"]]
    not_enumerated = [f for f in doc["factors_545_5"] if not f["enumerated"]]
    assert len(enumerated) == 4  # 545.5(c)(2)(i)-(iv)
    assert len(not_enumerated) == 2  # reached via (c)(1) + (f) only


def test_provenance_has_no_unverified_entries():
    doc = export()
    assert doc["provenance"]["unverified"] == []
