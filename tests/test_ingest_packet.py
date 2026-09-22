from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from demurragedesk import fixtures
from demurragedesk.ingest import (
    DEFAULT_COLUMN_MAP,
    load_column_map,
    read_csv,
    read_pdf_invoice,
    read_text_invoice,
)
from demurragedesk.packet import (
    DISCLAIMER,
    PacketParty,
    fmc_complaint_packet,
    mitigation_letter,
    write_packet,
    write_pdf,
)
from demurragedesk.screen import screen_invoice

CLEAN_CSV = """\
invoice_id,invoice_date,invoice_due_date,charge_last_incurred,charge_type,direction,\
billing_party,billed_party,container_number,bill_of_lading,port_of_discharge,\
basis_for_liability,free_time_days,free_time_start,free_time_end,\
container_availability_date,charged_dates,total_amount,total_amount_due,daily_rate,\
applicable_rule,specific_rate,dispute_contact,dispute_url,dispute_timeframes,\
cert_rules,cert_performance,dispute_window_days
CSV-1,2026-04-09,2026-05-09,2026-03-10,demurrage,import,Synthetic Lines,Importer LLC,\
SYNU1234567,SYNBL00042,Port of Example,contracting party per B/L,4,2026-03-03,2026-03-06,\
2026-03-02,2026-03-07;2026-03-08;2026-03-09;2026-03-10,1300.00,1300.00,325.00,\
Tariff SYN-100 rule 12,325.00/day,disputes@example.invalid,https://example.invalid/disputes,\
30 days to request; 30 days to resolve,yes,yes,30
"""


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# --- CSV ingest ------------------------------------------------------------


def test_csv_ingest_of_a_compliant_export_yields_no_defects(tmp_path):
    [rec] = read_csv(_write(tmp_path, "clean.csv", CLEAN_CSV))
    assert rec.container_number == "SYNU1234567"
    assert rec.total_amount == Decimal("1300.00")
    assert isinstance(rec.total_amount, Decimal)
    assert len(rec.charged_dates) == 4
    result = screen_invoice(rec)
    assert result.clean, [d.summary for d in result.defects]


def test_csv_blank_cell_is_a_missing_element_not_a_default(tmp_path):
    body = CLEAN_CSV.replace(",Tariff SYN-100 rule 12,", ",,")
    [rec] = read_csv(_write(tmp_path, "gap.csv", body))
    result = screen_invoice(rec)
    assert "541.6(c)(2)" in [d.element_key for d in result.defects]
    assert result.unpayable


def test_csv_late_invoice_detected_through_ingest(tmp_path):
    body = CLEAN_CSV.replace("CSV-1,2026-04-09", "CSV-1,2026-04-10")  # day 31
    [rec] = read_csv(_write(tmp_path, "late.csv", body))
    assert screen_invoice(rec).unpayable


def test_column_map_override(tmp_path):
    weird = CLEAN_CSV.replace("container_number", "Equipment ID", 1)
    mapfile = _write(
        tmp_path, "map.json", json.dumps({"container_number": ["Equipment ID"]})
    )
    cmap = load_column_map(mapfile)
    [rec] = read_csv(_write(tmp_path, "weird.csv", weird), cmap)
    assert rec.container_number == "SYNU1234567"
    # and without the override the field is simply absent -- not invented
    [rec2] = read_csv(_write(tmp_path, "weird2.csv", weird), DEFAULT_COLUMN_MAP)
    assert rec2.container_number == ""
    assert "541.6(a)(2)" in [d.element_key for d in screen_invoice(rec2).defects]


def test_csv_without_the_two_clock_dates_refuses_rather_than_guessing(tmp_path):
    body = CLEAN_CSV.replace(",2026-03-10,demurrage", ",,demurrage")
    with pytest.raises(ValueError, match="last incurred"):
        read_csv(_write(tmp_path, "noclock.csv", body))


# --- text / PDF reader -----------------------------------------------------

TEXT_INVOICE = """\
SYNTHETIC OCEAN LINES -- DEMURRAGE INVOICE
Invoice Number: TXT-77
Invoice Date: 2026-04-10
Charges through: 2026-03-10
Container Number: SYNU 123456 7
Bill of Lading: SYNBL00042
Port of Discharge: Port of Example, CA
Daily Rate: $325.00
Total Amount Due: $1,300.00
"""


def test_text_reader_extracts_what_it_can_and_names_what_it_cannot():
    res = read_text_invoice(TEXT_INVOICE)
    assert res.record is not None
    assert res.record.container_number == "SYNU1234567"
    assert res.record.invoice_issue_date == date(2026, 4, 10)
    assert res.record.charge_last_incurred == date(2026, 3, 10)
    assert res.record.total_amount == Decimal("1300.00")
    # It must NOT claim to have found the elements this invoice omits.
    for absent in (
        "free_time_days",
        "free_time_start",
        "earliest_return_date",
        "cert_performance_did_not_contribute",
    ):
        assert absent in res.not_found
    assert "COULD NOT FIND" in res.report()
    # Day 31 from 2026-03-10.
    assert screen_invoice(res.record).unpayable


def test_text_reader_without_dates_builds_no_record():
    res = read_text_invoice("Some scanned garbage with no dates at all.")
    assert res.record is None
    assert "No record built" in res.report()


def test_pdf_roundtrip(tmp_path):
    pdf = write_pdf(TEXT_INVOICE, tmp_path / "inv.pdf")
    res = read_pdf_invoice(pdf)
    assert res.record is not None
    assert res.record.charge_last_incurred == date(2026, 3, 10)
    assert res.not_found


# --- packets ---------------------------------------------------------------


PARTIES = PacketParty(
    billed_party="Synthetic Importer LLC",
    billed_party_contact="ops@importer.invalid",
    preparer="DemurrageDesk",
    billing_party="Synthetic Ocean Lines",
    billing_party_contact="billing@lines.invalid",
)


def test_mitigation_letter_cites_rule_and_defect():
    result = screen_invoice(fixtures.day31_invoice())
    body = mitigation_letter(result, PARTIES, today=date(2026, 4, 15))
    assert "REQUEST FOR FEE MITIGATION, REFUND, OR WAIVER" in body
    assert "46 CFR 541.8" in body
    assert "46 CFR 541.7(a)" in body
    assert "within thirty (30) calendar days from the date on which the charge" in body
    assert "SYN-0002-LATE" in body
    assert "FACTUAL COVER SUMMARY" in body
    assert "waiver of the charge in full" in body
    assert "2026-05-15" in body  # 541.8(b) response deadline, 30d out
    assert DISCLAIMER in body
    assert "billed party (or its authorised representative)" in body
    assert "not legal advice" in body


def test_fmc_packet_cites_41310_and_lists_every_defect():
    result = screen_invoice(fixtures.missing_elements_invoice())
    body = fmc_complaint_packet(
        result,
        PARTIES,
        mitigation_requested_on=date(2026, 4, 20),
        amount_paid=Decimal("1300.00"),
        today=date(2026, 6, 1),
    )
    assert "46 U.S.C. 41310" in body
    assert "order the refund of charges paid" in body
    for key in ("541.6(b)(3)", "541.6(c)(2)", "541.6(d)(2)", "541.6(e)(2)"):
        assert key in body
    assert "2026-05-20" in body  # 541.8(b) deadline from the request
    assert "Amount paid to date:   $1300.00" in body
    assert DISCLAIMER in body


def test_packet_quotes_545_5_verbatim_and_flags_nothing_as_unretrieved():
    """The gap this build closed: 545.5 is quoted, not hedged."""
    result = screen_invoice(fixtures.port_closure_invoice())
    body = mitigation_letter(result, PARTIES, today=date(2026, 4, 15))
    assert "545.5" in body
    assert "financial incentives to promote freight fluidity" in body
    assert "not retrieved verbatim" not in body
    assert "NOT retrieved" not in body


def test_clean_invoice_packet_says_so():
    result = screen_invoice(fixtures.clean_invoice())
    body = mitigation_letter(result, PARTIES, today=date(2026, 4, 15))
    assert "No defects identified." in body
    assert "Defects identified: 0" in body


def test_write_packet_emits_both_documents(tmp_path):
    result = screen_invoice(fixtures.day31_invoice())
    written = write_packet(result, PARTIES, tmp_path, pdf=True, today=date(2026, 4, 15))
    names = sorted(p.name for p in written)
    assert any("541-8_mitigation_request.txt" in n for n in names)
    assert any("FMC_41310_complaint.txt" in n for n in names)
    assert sum(n.endswith(".pdf") for n in names) == 2
    for p in written:
        assert p.exists() and p.stat().st_size > 500
