"""Pin the one real, verified data point in the corpus: FMC Docket CC-002.

See data/real/SOURCES.md and data/real/MEASURED.md for what this is and, at
length, what it is not. This test exists so the real-case finding cannot
silently drift if rules.py or screen.py change -- a real Commission finding
is a stronger regression signal than a synthetic fixture.
"""

from __future__ import annotations

from pathlib import Path

from demurragedesk.ingest import read_text_invoice
from demurragedesk.screen import screen_invoice

REAL_DIR = Path(__file__).resolve().parent.parent / "data" / "real"
CC002_RECORD = REAL_DIR / "cc002_reissued_invoice_001.txt"


def test_cc002_source_files_present():
    """The corpus wasn't silently deleted out from under the pinned test."""
    assert CC002_RECORD.exists()
    assert (REAL_DIR / "fmc_cc002_order_to_show_cause_20260306.pdf").exists()
    assert (REAL_DIR / "SOURCES.md").exists()
    assert (REAL_DIR / "MEASURED.md").exists()


def test_cc002_541_7a_matches_the_real_fmc_finding():
    """46 CFR 541.7(a): the tool must reproduce the arithmetic the order states.

    FMC Docket CC-002 order, paragraphs 18-32 (real order, served 2026-03-06):
    the reissued invoice was issued 142 calendar days after the date the
    charge was last incurred (the low end of the order's stated 142-316 day
    range for the 159 reissued invoices), which the Commission found violated
    46 CFR 541.7(a). This is the single real-world data point in the
    corpus -- see data/real/MEASURED.md.
    """
    text = CC002_RECORD.read_text(encoding="utf-8")
    res = read_text_invoice(text, invoice_id="CC002-ATTACHMENT-A-REISSUED-001")
    assert res.record is not None, "issue date and last-incurred date must both parse"

    result = screen_invoice(res.record)
    assert result.unpayable

    late_defects = [d for d in result.unpayable_defects if d.code == "LATE_INVOICE"]
    assert len(late_defects) == 1
    defect = late_defects[0]
    assert defect.cite == "46 CFR 541.7(a)"
    assert "142 calendar days" in defect.summary
    assert "112 day(s) beyond" in defect.summary


def test_cc002_541_6_elements_are_not_asserted_as_a_true_miss():
    """The 541.6 element check fires on this record, but that is NOT a
    measured true-miss rate -- the public FMC order never discloses whether
    the real invoice carried those fields. MEASURED.md documents this
    explicitly; this test just pins that every non-timing field genuinely
    came back "not found" (i.e. we are not accidentally asserting knowledge
    we don't have), so nobody quietly turns this into a false completeness
    claim later.
    """
    text = CC002_RECORD.read_text(encoding="utf-8")
    res = read_text_invoice(text, invoice_id="CC002-ATTACHMENT-A-REISSUED-001")
    assert res.record is not None

    # Only what the public order actually states should have been found.
    assert set(res.found) <= {
        "invoice_id",
        "invoice_date",
        "invoice_issue_date",
        "charge_last_incurred",
    }
    assert res.record.container_number == ""
    assert res.record.bill_of_lading == ""
