"""46 CFR 545.5 reasonableness screening, the unknown-fact state, and the
UNPAYABLE / DISPUTABLE separation in rendered output.

The three things under test, in order of commercial importance:

1. A 545.5 ground NEVER makes a charge unpayable. It is an argument that needs
   facts. Part 541 defects are what make a charge unpayable.
2. An unknown fact is NOT an allegation and NOT a waiver. It is an
   EvidenceGap, and it must say "not asserted - needs client evidence".
3. The rendered packet must keep the two apart, with Part A first.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from demurragedesk import fixtures
from demurragedesk.packet import (
    DISPUTABLE_LEAD,
    UNPAYABLE_LEAD,
    PacketParty,
    fmc_complaint_packet,
    mitigation_letter,
)
from demurragedesk.rules import (
    CHARGE_COMPLAINT_GUIDANCE,
    FACTORS_545_5,
    FORMAL_COMPLAINT_502_62,
    RULE_545_5,
    SMALL_CLAIMS_502_S,
    Consequence,
)
from demurragedesk.screen import DisputeFacts, screen_invoice

PARTIES = PacketParty(
    billed_party="Synthetic Importer LLC",
    preparer="DemurrageDesk",
    billing_party="Synthetic Ocean Lines",
)

# Two of the four charged days.
TWO_DAYS = (date(2026, 3, 8), date(2026, 3, 9))


def f545(result):
    return [d for d in result.defects if d.code == "UNREASONABLE_545_5"]


# --- the rule text itself ---------------------------------------------------


def test_545_5_is_retrieved_verbatim_not_paraphrased():
    assert RULE_545_5["verified"] == "VERBATIM"
    assert "financial incentives to promote freight fluidity" in RULE_545_5["text"]
    assert "Nothing in this rule precludes" in RULE_545_5["non_preclusion"]
    assert RULE_545_5["authority"] == "[85 FR 29665, May 18, 2020]"


def test_enumerated_factors_are_exactly_the_four_the_rule_lists():
    """545.5(c)(2) lists four. Everything else is (c)(1)+(f), and says so."""
    enumerated = {f.key for f in FACTORS_545_5 if f.enumerated}
    assert enumerated == {
        "545.5(c)(2)(i)",
        "545.5(c)(2)(ii)",
        "545.5(c)(2)(iii)",
        "545.5(c)(2)(iv)",
    }
    for factor in FACTORS_545_5:
        if not factor.enumerated:
            assert factor.key == "545.5(c)(1), (f)"


# --- each factor ------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name,value,expect_cite,expect_enumerated",
    [
        ("cargo_not_available_dates", TWO_DAYS, "545.5(c)(2)(i)", True),
        ("empty_return_refused_dates", TWO_DAYS, "545.5(c)(2)(ii)", True),
        ("notice_of_availability_given", False, "545.5(c)(2)(iii)", True),
        ("government_hold_dates", TWO_DAYS, "545.5(c)(2)(iv)", True),
        ("appointment_unavailable_dates", TWO_DAYS, "545.5(c)(1), (f)", False),
        ("charge_could_not_incentivise", True, "545.5(c)(1), (f)", False),
    ],
)
def test_each_factor_screens_as_disputable_with_its_own_cite(
    field_name, value, expect_cite, expect_enumerated
):
    result = screen_invoice(fixtures.facts_invoice(**{field_name: value}))
    found = f545(result)
    assert len(found) == 1, [d.cite for d in found]
    d = found[0]
    assert expect_cite in d.cite
    assert d.consequence is Consequence.DISPUTABLE
    # A 545.5 ground must NEVER void the charge on its face.
    assert not result.unpayable
    if expect_enumerated:
        assert "is an enumerated factor" in d.summary
    else:
        assert "NOT enumerated in 46 CFR 545.5" in d.summary
        assert "545.5(f)" in d.summary


def test_terminal_closure_is_screened_and_labelled_non_enumerated():
    result = screen_invoice(fixtures.facts_invoice(terminal_closed_dates=TWO_DAYS))
    closure = [d for d in result.defects if d.code == "ACCRUAL_DURING_CLOSURE"]
    assert len(closure) == 1
    assert "545.5(c)(1), (f)" in closure[0].cite
    assert closure[0].consequence is Consequence.DISPUTABLE
    assert not result.unpayable


def test_factor_quantifies_only_the_overlap_with_charged_days():
    """A day the client asserts but that was never billed adds nothing."""
    asserted = TWO_DAYS + (date(2026, 5, 1),)  # 5/1 was never charged
    result = screen_invoice(fixtures.facts_invoice(government_hold_dates=asserted))
    d = f545(result)[0]
    assert "2026-05-01" not in d.summary
    assert "2026-03-08" in d.summary and "2026-03-09" in d.summary
    # 2 overlapping days x $325.00
    assert "$650.00" in d.summary
    assert "asserted_days=2" in d.math


def test_no_overlap_means_no_factor_defect():
    result = screen_invoice(
        fixtures.facts_invoice(cargo_not_available_dates=(date(2026, 5, 1),))
    )
    assert f545(result) == []


# --- the unknown-fact state -------------------------------------------------


def test_unknown_facts_are_never_alleged_and_never_waived():
    """The default record asserts nothing, so it alleges nothing."""
    result = screen_invoice(fixtures.clean_invoice())
    assert f545(result) == []
    assert result.clean
    # ...but every factor is listed as needing evidence, including closure.
    fields = {g.fact_field for g in result.evidence_needed}
    assert fields == {f.fact_field for f in FACTORS_545_5} | {"terminal_closed_dates"}
    for gap in result.evidence_needed:
        assert gap.state == "not asserted - needs client evidence"
        assert gap.evidence  # we always say what would be needed


def test_asserted_negative_is_not_the_same_as_unknown():
    """() and False mean 'client checked, does not apply': no defect, no gap."""
    result = screen_invoice(
        fixtures.facts_invoice(
            cargo_not_available_dates=(),
            notice_of_availability_given=True,
        )
    )
    assert f545(result) == []
    fields = {g.fact_field for g in result.evidence_needed}
    assert "cargo_not_available_dates" not in fields
    assert "notice_of_availability_given" not in fields
    # the ones still unknown remain listed
    assert "government_hold_dates" in fields


def test_a_supplied_fact_removes_only_its_own_gap():
    result = screen_invoice(fixtures.facts_invoice(empty_return_refused_dates=TWO_DAYS))
    fields = {g.fact_field for g in result.evidence_needed}
    assert "empty_return_refused_dates" not in fields
    assert len(fields) == len(FACTORS_545_5)  # 5 factors left + closure


def test_evidence_gaps_are_serialised():
    result = screen_invoice(fixtures.clean_invoice())
    payload = result.as_dict()
    assert payload["evidence_needed"]
    assert all(
        g["state"] == "not asserted - needs client evidence"
        for g in payload["evidence_needed"]
    )
    assert payload["unpayable_defects"] == []
    assert payload["disputable_defects"] == []


# --- UNPAYABLE / DISPUTABLE separation in rendered output -------------------


def _both_kinds():
    """Day-31 invoice (UNPAYABLE, 541.7(a)) plus asserted 545.5 facts."""
    rec = fixtures.day31_invoice()
    rec.facts = DisputeFacts(
        government_hold_dates=TWO_DAYS, charge_could_not_incentivise=True
    )
    return screen_invoice(rec)


def test_result_partitions_defects_by_consequence():
    result = _both_kinds()
    assert result.unpayable_defects
    assert result.disputable_defects
    assert all(d.consequence is Consequence.UNPAYABLE for d in result.unpayable_defects)
    assert all(
        d.consequence is Consequence.DISPUTABLE for d in result.disputable_defects
    )
    # No defect is counted in both buckets.
    assert not set(result.unpayable_defects) & set(result.disputable_defects)


def test_rendered_letter_puts_part_a_first_and_does_not_dilute_it():
    body = mitigation_letter(_both_kinds(), PARTIES, today=date(2026, 4, 15))
    a = body.index("PART A -- CHARGE NOT PAYABLE ON THE FACE OF THE INVOICE")
    b = body.index("PART B -- CHARGE DISPUTABLE AS UNREASONABLE")
    assert a < b, "the unpayable ground must lead"
    assert UNPAYABLE_LEAD in body
    assert DISPUTABLE_LEAD in body
    assert "PART A IS THE PRIMARY GROUND" in body
    assert "never in substitution for it" in body
    # The 541.7(a) ground and the 545.5 ground are both present, separately.
    assert "46 CFR 541.7(a)" in body
    assert "545.5(c)(2)(iv)" in body


def test_a_545_5_only_invoice_says_plainly_it_is_not_unpayable():
    result = screen_invoice(fixtures.facts_invoice(empty_return_refused_dates=TWO_DAYS))
    assert not result.unpayable
    body = mitigation_letter(result, PARTIES, today=date(2026, 4, 15))
    assert "does NOT contend the charge is unpayable on its face" in body
    assert "PART A IS THE PRIMARY GROUND" not in body
    assert "545.5(c)(2)(ii)" in body


def test_cover_summary_counts_the_two_kinds_separately():
    body = mitigation_letter(_both_kinds(), PARTIES, today=date(2026, 4, 15))
    assert "UNPAYABLE (46 CFR part 541, face of the document): 1" in body
    assert "DISPUTABLE (46 CFR 545.5 reasonableness, needs facts): 2" in body


def test_packet_renders_the_unknown_facts_section():
    body = mitigation_letter(
        screen_invoice(fixtures.clean_invoice()), PARTIES, today=date(2026, 4, 15)
    )
    assert "FACTS NOT ASSERTED -- NEEDS CLIENT EVIDENCE" in body
    assert "not asserted - needs client evidence" in body
    assert "neither alleged nor waived" in body
    assert "cannot affect Part A" in body


# --- FMC charge-complaint procedure alignment -------------------------------


def test_fmc_packet_checklist_matches_the_commissions_own_guidance():
    body = fmc_complaint_packet(
        _both_kinds(), PARTIES, today=date(2026, 6, 1), amount_paid=Decimal("0")
    )
    for item in CHARGE_COMPLAINT_GUIDANCE["required"]:
        assert item in body, item
    assert "chargecomplaints@fmc.gov" in body
    assert CHARGE_COMPLAINT_GUIDANCE["who"] in body
    assert "June 16, 2022" in body


def test_fmc_packet_states_the_escalation_routes_with_their_thresholds():
    body = fmc_complaint_packet(_both_kinds(), PARTIES, today=date(2026, 6, 1))
    assert SMALL_CLAIMS_502_S["cite"] in body
    assert "$50,000 or less" in body
    assert "$176 filing fee" in body
    assert FORMAL_COMPLAINT_502_62["cite"] in body
    assert "$387 filing fee" in body
    assert "within three years" in body
    for item in FORMAL_COMPLAINT_502_62["contents"]:
        assert item in body, item[:60]


def test_fmc_packet_keeps_the_two_grounds_separate_too():
    body = fmc_complaint_packet(_both_kinds(), PARTIES, today=date(2026, 6, 1))
    assert body.index("PART A") < body.index("PART B")
    assert "46 U.S.C. 41310" in body
