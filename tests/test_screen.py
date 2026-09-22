from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from demurragedesk import fixtures
from demurragedesk.rules import (
    CLOCKS,
    REQUIRED_ELEMENTS,
    Consequence,
    provenance,
    required_keys,
)
from demurragedesk.screen import as_date, as_money, screen_invoice


def codes(result):
    return sorted(d.code for d in result.defects)


# --- clean -----------------------------------------------------------------


def test_compliant_invoice_yields_no_defects():
    result = screen_invoice(fixtures.clean_invoice())
    assert result.defects == [], [d.summary for d in result.defects]
    assert result.clean
    assert not result.unpayable
    assert result.amount_at_issue == Decimal("0")


# --- 541.7 boundary --------------------------------------------------------


@pytest.mark.parametrize(
    "offset,expect_defect",
    [(0, False), (29, False), (30, False), (31, True), (45, True)],
)
def test_30_day_boundary_is_inclusive(offset, expect_defect):
    """541.7(a) permits issuance 'within thirty (30) calendar days'.

    Day 30 is within; day 31 is not.
    """
    rec = fixtures.clean_invoice()
    rec.invoice_issue_date = rec.charge_last_incurred + timedelta(days=offset)
    result = screen_invoice(rec)
    assert ("LATE_INVOICE" in codes(result)) is expect_defect


def test_day31_invoice_is_unpayable_with_citation_and_math():
    result = screen_invoice(fixtures.day31_invoice())
    late = [d for d in result.defects if d.code == "LATE_INVOICE"]
    assert len(late) == 1
    d = late[0]
    assert d.cite == "46 CFR 541.7(a)"
    assert d.consequence is Consequence.UNPAYABLE
    assert "not required to pay the charge" in d.rule_text
    assert "day 31" in d.math
    assert "1 day(s) beyond" in d.summary
    assert result.unpayable
    assert result.amount_at_issue == result.record.total_amount


def test_deadline_math_is_exposed():
    result = screen_invoice(fixtures.clean_invoice())
    rec = result.record
    assert result.deadlines[
        "invoice_due_by_541_7a"
    ] == rec.charge_last_incurred + timedelta(days=30)
    assert result.deadlines[
        "mitigation_request_due_by_541_8a"
    ] == rec.invoice_issue_date + timedelta(days=30)


# --- 541.6 / 541.5 missing elements ---------------------------------------


def test_missing_elements_each_reported_once_and_unpayable():
    result = screen_invoice(fixtures.missing_elements_invoice())
    missing = [d for d in result.defects if d.code == "MISSING_REQUIRED_ELEMENT"]
    assert sorted(d.element_key for d in missing) == [
        "541.6(b)(3)",
        "541.6(c)(2)",
        "541.6(d)(2)",
        "541.6(e)(2)",
    ]
    for d in missing:
        assert d.consequence is Consequence.UNPAYABLE
        assert "46 CFR 541.5" in d.cite
        assert "eliminates any obligation" in d.summary
    assert result.unpayable


def test_every_required_element_is_individually_detectable():
    """Drop one element at a time; each must raise exactly its own defect."""
    for key in required_keys("import"):
        rec = fixtures.clean_invoice()
        rec.present_fields = fixtures.ALL_IMPORT_KEYS - {key}
        result = screen_invoice(rec)
        missing = [d for d in result.defects if d.code == "MISSING_REQUIRED_ELEMENT"]
        assert [d.element_key for d in missing] == [key], key


def test_export_invoice_requires_erd_not_pod():
    rec = fixtures.clean_invoice()
    rec.direction = "export"
    rec.present_fields = frozenset(required_keys("export"))
    assert screen_invoice(rec).clean
    # The import-only elements must NOT be demanded of an export invoice.
    keys = set(required_keys("export"))
    assert "541.6(b)(7)" in keys
    assert "541.6(a)(3)" not in keys and "541.6(b)(6)" not in keys


# --- 541.7(b) NVOCC --------------------------------------------------------


def test_nvocc_rebill_clock_runs_from_upstream_invoice():
    rec = fixtures.nvocc_rebill_invoice(late=True)
    # Sanity: it would have PASSED under 541.7(a).
    assert (rec.invoice_issue_date - rec.charge_last_incurred).days <= 30
    result = screen_invoice(rec)
    late = [d for d in result.defects if d.code == "LATE_INVOICE"]
    assert len(late) == 1
    assert late[0].cite == "46 CFR 541.7(b)"
    assert "upstream invoice issuance date" in late[0].math
    assert result.unpayable


def test_nvocc_rebill_on_day_30_is_clean():
    assert screen_invoice(fixtures.nvocc_rebill_invoice(late=False)).clean


def test_nvocc_without_upstream_date_is_flagged_not_assumed():
    rec = fixtures.nvocc_rebill_invoice(late=True)
    rec.upstream_invoice_issue_date = None
    result = screen_invoice(rec)
    assert "NVOCC_ANCHOR_UNKNOWN" in codes(result)
    assert "LATE_INVOICE" not in codes(result)  # we do not guess the anchor


# --- port closure ----------------------------------------------------------


def test_charges_accruing_across_closure_are_disputable_and_quantified():
    result = screen_invoice(fixtures.port_closure_invoice())
    closure = [d for d in result.defects if d.code == "ACCRUAL_DURING_CLOSURE"]
    assert len(closure) == 1
    d = closure[0]
    assert d.consequence is Consequence.DISPUTABLE
    assert "2026-03-08" in d.summary and "2026-03-09" in d.summary
    assert "$650.00" in d.summary  # 2 days x 325.00
    # 46 CFR 545.5 is now retrieved verbatim, so it is QUOTED, not flagged.
    assert d.verified == "VERBATIM"
    assert "financial incentives to promote freight fluidity" in d.rule_text
    # Terminal closure is not an enumerated 545.5 factor; the cite must say so.
    assert "545.5(c)(1), (f)" in d.cite
    assert "not an enumerated 545.5 factor" in d.summary
    assert not result.unpayable  # closure alone does not void the charge


def test_no_closure_overlap_no_defect():
    rec = fixtures.port_closure_invoice()
    rec.closure_dates = (date(2026, 4, 1),)
    assert "ACCRUAL_DURING_CLOSURE" not in codes(screen_invoice(rec))


# --- 541.8(a) --------------------------------------------------------------


def test_short_dispute_window_is_disputable():
    rec = fixtures.clean_invoice()
    rec.stated_dispute_window_days = 14
    result = screen_invoice(rec)
    d = next(x for x in result.defects if x.code == "SHORT_DISPUTE_WINDOW")
    assert d.cite == "46 CFR 541.8(a)"
    assert d.consequence is Consequence.DISPUTABLE
    assert "at least thirty (30) calendar days" in d.rule_text


def test_dispute_window_of_exactly_30_is_fine():
    rec = fixtures.clean_invoice()
    rec.stated_dispute_window_days = 30
    assert "SHORT_DISPUTE_WINDOW" not in codes(screen_invoice(rec))


# --- 541.4 -----------------------------------------------------------------


def test_541_4_is_vacated_and_raises_nothing():
    """eCFR 2026-09-01 reads '§ 541.4 [Reserved]'. A vacated section must never
    produce a defect, and provenance must say VACATED rather than drop it."""
    from demurragedesk.rules import RULE_541_4, VACATED, provenance

    assert RULE_541_4["verified"] == VACATED
    rec = fixtures.clean_invoice()
    rec.also_invoiced_consignee = True
    assert "DOUBLE_BILLED" not in codes(screen_invoice(rec))
    rec2 = fixtures.clean_invoice()
    rec2.billed_party_role = "other"
    assert "IMPROPER_BILLED_PARTY" not in codes(screen_invoice(rec2))
    prov = provenance()
    assert prov["rules"]["46 CFR 541.4"] == VACATED
    assert prov["vacated"] == ["46 CFR 541.4", "46 CFR 502.303"]
    # The small-claims cite must never span the reserved section again.
    from demurragedesk.rules import SMALL_CLAIMS_502_S
    assert "502.303" not in SMALL_CLAIMS_502_S["cite"]
    assert "-" not in SMALL_CLAIMS_502_S["cite"]
    assert "46 CFR 541.4" not in prov["unverified"]


# --- arithmetic ------------------------------------------------------------


def test_total_not_ascertainable_from_stated_rate():
    rec = fixtures.clean_invoice()
    rec.total_amount = Decimal("1500.00")  # rate 325 x 4 days = 1300
    d = next(
        x for x in screen_invoice(rec).defects if x.code == "AMOUNT_NOT_ASCERTAINABLE"
    )
    assert "delta 200.00" in d.math


# --- coercion --------------------------------------------------------------


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="naive datetime"):
        as_date(datetime(2026, 3, 10, 23, 30))


def test_aware_datetime_needs_explicit_tz():
    aware = datetime(2026, 3, 10, 23, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="explicit tz"):
        as_date(aware)


def test_timezone_resolution_can_change_the_calendar_day():
    """23:30 UTC on the 10th is still the 10th in UTC, the 15th hour of the
    10th in Los Angeles -- but 00:30 UTC on the 11th is the 10th in LA. A
    demurrage clock that got this wrong would shift a payability finding."""
    aware = datetime(2026, 3, 11, 0, 30, tzinfo=timezone.utc)
    assert as_date(aware, timezone.utc) == date(2026, 3, 11)
    assert as_date(aware, timezone(timedelta(hours=-7))) == date(2026, 3, 10)


def test_float_money_is_rejected():
    with pytest.raises(TypeError, match="lossy"):
        as_money(1300.00)
    assert as_money("$1,300.00") == Decimal("1300.00")


# --- provenance ------------------------------------------------------------


def test_every_part_541_rule_is_verbatim_verified():
    prov = provenance()
    # 46 CFR 545.5 was retrieved on 2026-09-15; nothing is UNVERIFIED now.
    assert prov["unverified"] == []
    assert prov["rules"]["46 CFR 545.5"] == "VERBATIM"
    assert prov["rules"]["46 CFR 502.62"] == "VERBATIM"
    # 46 CFR 541.6: (a) 4 + (b) 8 + (c) 3 + (d) 3 + (e) 2 = 20 elements.
    assert len(REQUIRED_ELEMENTS) == 20
    assert len(required_keys("import")) == 19
    assert len(required_keys("export")) == 18  # no (a)(3) port of discharge, no (b)(6)
    assert all(c.days == 30 for c in CLOCKS.values())
