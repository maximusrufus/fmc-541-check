"""Every 46 CFR 541.6 element must be findable by every ingest path.

WHY THIS FILE EXISTS
--------------------
Presence detection looks an element up by ``RequiredElement.field_name``. The
ingest maps are keyed by ``InvoiceRecord`` attribute names. Those two
vocabularies are not identical, and where they diverge ``_pick`` finds nothing,
the element is recorded ABSENT, and 46 CFR 541.5 converts absence into
"eliminates any obligation of the billed party to pay the applicable charge".

So a naming mismatch does not degrade gracefully into a missed defect. It
manufactures a **FALSE UNPAYABLE** on a complete invoice -- the client repeats
it to the carrier, the carrier produces the invoice, and the claim collapses.

Found 2026-09-15: ``total_amount_due`` (541.6(c)(1)) and ``invoice_date``
(541.6(b)(1)) had no producer in the CSV path, and those two plus
``specific_rate`` (541.6(c)(3)) had none in the text/PDF path. Every CSV
invoice ever screened was reported unpayable on 541.6(c)(1) alone.

The coverage tests below fail on the whole BUG CLASS, not just those three.
"""

from __future__ import annotations

import csv
import io

import pytest

from demurragedesk.ingest import (
    DEFAULT_COLUMN_MAP,
    _LABELS,
    _record_from_row,
    read_text_invoice,
)
from demurragedesk.rules import ELEMENTS_BY_FIELD, REQUIRED_ELEMENTS
from demurragedesk.screen import screen_invoice

ELEMENT_FIELDS = [(e.key, e.field_name) for e in REQUIRED_ELEMENTS if e.field_name]


def missing_keys(result) -> set[str]:
    return {
        d.element_key
        for d in result.defects
        if d.code == "MISSING_REQUIRED_ELEMENT" and d.element_key
    }


# ---------------------------------------------------------------------------
# The class-killers: no element may be unfindable by any ingest path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,field_name", ELEMENT_FIELDS)
def test_every_element_field_name_has_a_csv_producer(key, field_name):
    """A field_name absent from the column map falls back to a literal column
    spelling of its own name, which real carrier exports never use -- so the
    element reads ABSENT and the charge reads unpayable. That is the defect."""
    assert field_name in DEFAULT_COLUMN_MAP, (
        f"{key} (field_name={field_name!r}) has no column-map producer. Ingest will mark it "
        f"absent on every CSV, and 541.5 will report a FALSE UNPAYABLE. Add it to "
        f"DEFAULT_COLUMN_MAP or to _ELEMENT_FIELD_ALIASES."
    )


@pytest.mark.parametrize("key,field_name", ELEMENT_FIELDS)
def test_every_element_field_name_has_a_text_producer(key, field_name):
    assert field_name in _LABELS, (
        f"{key} (field_name={field_name!r}) has no label producer. Ingest will mark it absent "
        f"on every text/PDF invoice, and 541.5 will report a FALSE UNPAYABLE. Add it to "
        f"_LABELS or to _ELEMENT_FIELD_ALIASES."
    )


def test_element_and_record_vocabularies_stay_reconciled():
    """Presence lookup must be total over the element vocabulary."""
    unresolvable = [
        e.key
        for e in REQUIRED_ELEMENTS
        if e.field_name and ELEMENTS_BY_FIELD.get(e.field_name) is None
    ]
    assert unresolvable == []


# ---------------------------------------------------------------------------
# Functional: a complete invoice must not be called unpayable
# ---------------------------------------------------------------------------

#: One value per element field_name, written against the FIRST documented spelling of each.
#: A key-coverage test alone would pass while the spelling was wrong; this one would not.
VALUES = {
    "bill_of_lading": "SYNBL00042",
    "container_number": "SYNU1234567",
    "port_of_discharge": "Port of Example, CA",
    "basis_for_liability": "consignee named on the bill of lading",
    "invoice_date": "2026-04-09",  # day 30 from the charge: timely
    "invoice_due_date": "2026-05-09",
    "free_time_days": "4",
    "free_time_start": "2026-03-03",
    "free_time_end": "2026-03-06",
    "container_availability_date": "2026-03-06",
    "earliest_return_date": "2026-03-06",
    "charged_dates": "2026-03-07;2026-03-08;2026-03-09;2026-03-10",
    "total_amount_due": "1300.00",
    "applicable_rule": "TARIFF-1 rule 5",
    "specific_rate": "325.00",
    "dispute_contact": "disputes@example.test",
    "dispute_digital_means": "https://example.test/disputes",
    "dispute_timeframes": "30 days to request, 30 days to resolve",
    "cert_consistent_with_rules": "yes",
    "cert_performance_did_not_contribute": "yes",
}


def complete_row(direction: str = "import") -> dict[str, str]:
    """A CSV row that populates every element required for ``direction``."""
    row: dict[str, str] = {}
    for el in REQUIRED_ELEMENTS:
        if not el.applicable(direction) or not el.field_name:
            continue
        spelling = DEFAULT_COLUMN_MAP[el.field_name][0]
        row[spelling] = VALUES[el.field_name]
    # Without this the record defaults to "import" and then demands the import-only elements
    # this row deliberately omits for an export move.
    row[DEFAULT_COLUMN_MAP["direction"][0]] = direction
    # The two fields the clock arithmetic needs, under their own spellings.
    row[DEFAULT_COLUMN_MAP["charge_last_incurred"][0]] = "2026-03-10"
    row[DEFAULT_COLUMN_MAP["invoice_issue_date"][0]] = "2026-04-09"
    row[DEFAULT_COLUMN_MAP["invoice_id"][0]] = "COVERAGE-1"
    return row


def screen_row(row: dict[str, str]):
    # Round-trip through real CSV text so quoting/BOM behaviour is exercised too.
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    parsed = next(csv.DictReader(io.StringIO(buf.getvalue())))
    return screen_invoice(_record_from_row(parsed, DEFAULT_COLUMN_MAP))


def test_complete_csv_invoice_reports_no_missing_element_at_all():
    """The regression: a populated total must not read as a missing 541.6(c)(1)."""
    result = screen_row(complete_row())
    assert missing_keys(result) == set(), (
        "a complete CSV invoice was reported as omitting required elements -- FALSE UNPAYABLE"
    )
    assert not result.unpayable
    assert result.clean


def test_complete_export_csv_invoice_reports_no_missing_element():
    result = screen_row(complete_row("export"))
    assert missing_keys(result) == set()
    assert not result.unpayable


def test_csv_invoice_actually_missing_the_total_still_reports_541_6_c_1():
    """The other half: the fix must not blind the screen to a real omission."""
    row = complete_row()
    del row[DEFAULT_COLUMN_MAP["total_amount_due"][0]]
    result = screen_row(row)
    assert "541.6(c)(1)" in missing_keys(result)
    assert result.unpayable


def test_csv_invoice_with_an_empty_total_column_still_reports_541_6_c_1():
    """Present-but-blank is an omission, not a value."""
    row = complete_row()
    row[DEFAULT_COLUMN_MAP["total_amount_due"][0]] = ""
    assert "541.6(c)(1)" in missing_keys(screen_row(row))


@pytest.mark.parametrize("key", ["541.6(b)(1)", "541.6(c)(1)", "541.6(c)(3)"])
def test_text_invoice_finds_the_elements_that_had_no_label_producer(key):
    """The three elements the text/PDF path could never find before."""
    text = (
        "SYNTHETIC OCEAN LINES -- DEMURRAGE INVOICE\n"
        "Invoice number: TXT-1\n"
        "Invoice date: 2026-04-09\n"
        "Charges through: 2026-03-10\n"
        "Container number: SYNU1234567\n"
        "Total amount due: $1300.00\n"
        "Daily rate: $325.00\n"
    )
    res = read_text_invoice(text)
    assert res.record is not None, res.report()
    assert key in res.record.present_fields, (
        f"{key} was not found in a text invoice that plainly states it; "
        f"found: {sorted(res.record.present_fields)}"
    )
