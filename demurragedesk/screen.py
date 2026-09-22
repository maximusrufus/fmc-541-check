"""Screen a parsed demurrage/detention invoice against 46 CFR part 541.

Design rules:
  * All calendar arithmetic happens on ``datetime.date`` only.  A wall-clock
    instant is converted to a calendar date exactly once, explicitly, at the
    boundary (:func:`as_date`), against a named timezone.  Naive datetimes are
    REJECTED rather than silently assumed to be UTC or local -- a demurrage
    clock that slips a day changes whether a charge is payable.
  * All money is :class:`decimal.Decimal`.  Floats are rejected.
  * Every defect carries the citation, the verbatim rule text, the
    consequence, and the arithmetic that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from typing import Any, Iterable

from . import rules
from .rules import (
    CLOCKS,
    CLOSURE_FACTOR,
    FACTORS_545_5,
    REQUIRED_ELEMENTS,
    RULE_541_4,
    RULE_541_5,
    RULE_545_5,
    Consequence,
    ReasonablenessFactor,
)

__all__ = [
    "DisputeFacts",
    "EvidenceGap",
    "InvoiceRecord",
    "Defect",
    "ScreenResult",
    "as_date",
    "as_money",
    "screen_invoice",
]


# ---------------------------------------------------------------------------
# Boundary coercion
# ---------------------------------------------------------------------------


def as_date(value: Any, tz: tzinfo | None = None) -> date:
    """Coerce ``value`` to a calendar :class:`date`, timezone-safely.

    * ``date``            -> returned as-is (already a calendar date).
    * aware ``datetime``  -> converted to ``tz`` (required) then ``.date()``.
    * naive ``datetime``  -> ``ValueError``; the caller must state the zone.
    * ``str``             -> ISO 8601; an offset-bearing string needs ``tz``.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip())
        if value.hour == 0 and value.minute == 0 and value.tzinfo is None:
            return value.date()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime is ambiguous for a calendar-day rule; pass a "
                "date, or an aware datetime plus the tz to resolve it in"
            )
        if tz is None:
            raise ValueError(
                "an aware datetime needs an explicit tz to resolve to a "
                "calendar date (e.g. the port's local zone)"
            )
        return value.astimezone(tz).date()
    if isinstance(value, date):
        return value
    raise TypeError(f"cannot interpret {value!r} as a calendar date")


def as_money(value: Any) -> Decimal:
    """Coerce to Decimal.  Floats are rejected -- binary money is a defect."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("float money is lossy; pass Decimal or a string")
    if isinstance(value, (int, str)):
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    raise TypeError(f"cannot interpret {value!r} as money")


UTC = timezone.utc


# ---------------------------------------------------------------------------
# Facts behind a 46 CFR 545.5 reasonableness argument
# ---------------------------------------------------------------------------


@dataclass
class DisputeFacts:
    """Facts the BILLED PARTY supplies; nothing here is ever inferred.

    Every field is tri-state, and the middle state is the point:

    * ``None``           -- NOT ASSERTED. The client has not told us. This is
                            the default, and it produces an
                            :class:`EvidenceGap`, never a defect.
    * ``()`` / ``False`` -- asserted and negative. The client checked and the
                            factor does not apply. No defect, and no gap.
    * non-empty / ``True`` -- asserted and positive. Screens into a DISPUTABLE
                            finding under 46 CFR 545.5.

    Conflating "unknown" with "no" is the failure mode this class exists to
    prevent: an unasserted fact must never quietly become a waived argument,
    and it must never quietly become an alleged one.
    """

    #: Dates the container/cargo was not available for retrieval.
    cargo_not_available_dates: tuple[date, ...] | None = None
    #: Dates no terminal appointment could be obtained.
    appointment_unavailable_dates: tuple[date, ...] | None = None
    #: Dates an empty return was refused or empty receiving was restricted.
    empty_return_refused_dates: tuple[date, ...] | None = None
    #: Dates the container was under a government hold or exam.
    government_hold_dates: tuple[date, ...] | None = None
    #: Dates the terminal/port was closed. Overrides ``InvoiceRecord.closure_dates``.
    terminal_closed_dates: tuple[date, ...] | None = None
    #: Whether the billing party gave notice that the cargo was available.
    notice_of_availability_given: bool | None = None
    #: Whether the charge could not have incentivised any act by the billed party.
    charge_could_not_incentivise: bool | None = None

    def __post_init__(self) -> None:
        for fname in (
            "cargo_not_available_dates",
            "appointment_unavailable_dates",
            "empty_return_refused_dates",
            "government_hold_dates",
            "terminal_closed_dates",
        ):
            v = getattr(self, fname)
            if v is not None:
                setattr(self, fname, tuple(as_date(d) for d in v))

    def asserted(self, field_name: str) -> bool:
        """True when the client has actually told us about ``field_name``."""
        return getattr(self, field_name) is not None


@dataclass(frozen=True)
class EvidenceGap:
    """A 545.5 factor we could NOT assert because the fact is unknown."""

    factor_key: str
    cite: str
    label: str
    fact_field: str
    evidence: str
    state: str = "not asserted - needs client evidence"

    def as_dict(self) -> dict:
        return {
            "factor_key": self.factor_key,
            "cite": self.cite,
            "label": self.label,
            "fact_field": self.fact_field,
            "evidence": self.evidence,
            "state": self.state,
        }


# ---------------------------------------------------------------------------
# The record under screen
# ---------------------------------------------------------------------------


@dataclass
class InvoiceRecord:
    """A parsed demurrage/detention invoice.

    ``present_fields`` is the set of 46 CFR 541.6 element keys (e.g.
    ``"541.6(b)(4)"``) that the invoice actually contains.  Ingest populates it
    from what it could *find*; anything it could not find is simply absent, and
    absence is what 541.5 punishes.  We never infer presence.
    """

    invoice_id: str
    invoice_issue_date: date
    charge_last_incurred: date
    charge_type: str = "demurrage"  # demurrage | detention
    direction: str = "import"  # import | export
    billing_party: str = ""
    billing_party_type: str = "ocean_common_carrier"  # ..._carrier | mto | nvocc
    billed_party: str = ""
    billed_party_role: str = (
        "contracting_party"  # contracting_party | consignee | other
    )
    container_number: str = ""
    bill_of_lading: str = ""
    port_of_discharge: str = ""
    total_amount: Decimal = Decimal("0")
    daily_rate: Decimal | None = None
    free_time_days: int | None = None
    charge_first_incurred: date | None = None
    charged_dates: tuple[date, ...] = ()
    closure_dates: tuple[date, ...] = ()  # port/terminal closed or inaccessible
    closure_reason: str = ""
    stated_dispute_window_days: int | None = None  # what the invoice itself allows
    upstream_invoice_issue_date: date | None = None  # NVOCC: invoice it received
    also_invoiced_consignee: bool = False  # 541.4 double-billing flag
    present_fields: frozenset[str] = frozenset()
    unresolved_fields: tuple[str, ...] = ()  # ingest could not find these
    #: Client-supplied facts behind a 46 CFR 545.5 argument. Default = all unknown.
    facts: DisputeFacts = field(default_factory=DisputeFacts)
    source: str = ""

    def __post_init__(self) -> None:
        self.invoice_issue_date = as_date(self.invoice_issue_date)
        self.charge_last_incurred = as_date(self.charge_last_incurred)
        if self.charge_first_incurred is not None:
            self.charge_first_incurred = as_date(self.charge_first_incurred)
        if self.upstream_invoice_issue_date is not None:
            self.upstream_invoice_issue_date = as_date(self.upstream_invoice_issue_date)
        self.charged_dates = tuple(as_date(d) for d in self.charged_dates)
        self.closure_dates = tuple(as_date(d) for d in self.closure_dates)
        self.total_amount = as_money(self.total_amount)
        if self.daily_rate is not None:
            self.daily_rate = as_money(self.daily_rate)
        self.present_fields = frozenset(self.present_fields)
        if self.direction not in ("import", "export"):
            raise ValueError("direction must be 'import' or 'export'")


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Defect:
    code: str
    cite: str
    rule_text: str
    consequence: Consequence
    summary: str
    math: str = ""
    element_key: str | None = None
    verified: str = rules.VERBATIM

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "cite": self.cite,
            "consequence": self.consequence.value,
            "summary": self.summary,
            "math": self.math,
            "rule_text": self.rule_text,
            "element_key": self.element_key,
            "verified": self.verified,
        }


@dataclass
class ScreenResult:
    record: InvoiceRecord
    defects: list[Defect] = field(default_factory=list)
    deadlines: dict[str, date] = field(default_factory=dict)
    #: 545.5 factors that could not be asserted because the fact is unknown.
    evidence_needed: list[EvidenceGap] = field(default_factory=list)

    @property
    def unpayable(self) -> bool:
        return any(d.consequence is Consequence.UNPAYABLE for d in self.defects)

    @property
    def unpayable_defects(self) -> list[Defect]:
        """46 CFR 541 billing defects -- visible on the face of the document."""
        return [d for d in self.defects if d.consequence is Consequence.UNPAYABLE]

    @property
    def disputable_defects(self) -> list[Defect]:
        """Arguments that need facts; they do NOT extinguish the obligation."""
        return [d for d in self.defects if d.consequence is Consequence.DISPUTABLE]

    @property
    def substantive_defects(self) -> list[Defect]:
        return [
            d for d in self.defects if d.consequence is not Consequence.INFORMATIONAL
        ]

    @property
    def clean(self) -> bool:
        return not self.substantive_defects

    @property
    def amount_at_issue(self) -> Decimal:
        return self.record.total_amount if not self.clean else Decimal("0")

    def as_dict(self) -> dict:
        return {
            "invoice_id": self.record.invoice_id,
            "unpayable": self.unpayable,
            "clean": self.clean,
            "amount_at_issue": str(self.amount_at_issue),
            "defects": [d.as_dict() for d in self.defects],
            "unpayable_defects": [d.as_dict() for d in self.unpayable_defects],
            "disputable_defects": [d.as_dict() for d in self.disputable_defects],
            "evidence_needed": [g.as_dict() for g in self.evidence_needed],
            "deadlines": {k: v.isoformat() for k, v in self.deadlines.items()},
        }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_issuance_clock(rec: InvoiceRecord) -> list[Defect]:
    """46 CFR 541.7(a) and, for an NVOCC billing party, 541.7(b)."""
    out: list[Defect] = []
    if rec.billing_party_type == "nvocc":
        clock = CLOCKS["541.7(b)"]
        anchor = rec.upstream_invoice_issue_date
        if anchor is None:
            out.append(
                Defect(
                    code="NVOCC_ANCHOR_UNKNOWN",
                    cite=clock.cite,
                    rule_text=clock.text,
                    consequence=Consequence.DISPUTABLE,
                    summary=(
                        "Billing party is an NVOCC, so its 30-day window runs from "
                        "the issuance date of the invoice IT received, which this "
                        "invoice does not disclose. The billed party cannot verify "
                        "timeliness without it."
                    ),
                    math="upstream invoice issuance date: NOT STATED",
                )
            )
            return out
        anchor_label = "upstream invoice issuance date"
    else:
        clock = CLOCKS["541.7(a)"]
        anchor = rec.charge_last_incurred
        anchor_label = "date charge last incurred"

    deadline = anchor + timedelta(days=clock.days)
    elapsed = (rec.invoice_issue_date - anchor).days
    math = (
        f"{anchor_label} {anchor.isoformat()} + {clock.days} calendar days "
        f"= {deadline.isoformat()}; invoice issued "
        f"{rec.invoice_issue_date.isoformat()} (day {elapsed})"
    )
    if elapsed > clock.days:
        out.append(
            Defect(
                code="LATE_INVOICE",
                cite=clock.cite,
                rule_text=clock.text,
                consequence=Consequence.UNPAYABLE,
                summary=(
                    f"Invoice was issued {elapsed} calendar days after the "
                    f"{anchor_label}, {elapsed - clock.days} day(s) beyond the "
                    f"{clock.days}-day limit. The billed party is not required to "
                    f"pay the charge."
                ),
                math=math,
            )
        )
    return out


def _check_required_elements(rec: InvoiceRecord) -> list[Defect]:
    """46 CFR 541.6 contents; consequence supplied by 46 CFR 541.5."""
    out: list[Defect] = []
    for el in REQUIRED_ELEMENTS:
        if not el.applicable(rec.direction):
            continue
        if el.key in rec.present_fields:
            continue
        out.append(
            Defect(
                code="MISSING_REQUIRED_ELEMENT",
                cite=f"{el.cite} (consequence: {RULE_541_5['cite']})",
                rule_text=f"{rules.GROUP_LEADS[el.group]} {el.text}",
                consequence=Consequence.UNPAYABLE,
                summary=(
                    f"The invoice omits a required minimum element: {el.text.rstrip('; and')}"
                    f" Under {RULE_541_5['cite']}, omission of any required minimum "
                    f"information eliminates any obligation to pay the applicable charge."
                ),
                math=f"{el.key} present: no",
                element_key=el.key,
                verified=el.verified,
            )
        )
    return out


def _check_dispute_window(rec: InvoiceRecord) -> list[Defect]:
    """46 CFR 541.8(a) -- at least 30 days must be allowed."""
    clock = CLOCKS["541.8(a)"]
    stated = rec.stated_dispute_window_days
    if stated is None or stated >= clock.days:
        return []
    return [
        Defect(
            code="SHORT_DISPUTE_WINDOW",
            cite=clock.cite,
            rule_text=clock.text,
            consequence=Consequence.DISPUTABLE,
            summary=(
                f"The invoice allows only {stated} calendar days to request "
                f"mitigation, refund, or waiver. At least {clock.days} calendar "
                f"days from the invoice issuance date must be allowed."
            ),
            math=(
                f"stated window {stated}d < required {clock.days}d; lawful floor "
                f"= {(rec.invoice_issue_date + timedelta(days=clock.days)).isoformat()}"
            ),
        )
    ]


def _check_billing_recipient(rec: InvoiceRecord) -> list[Defect]:
    """46 CFR 541.4 is vacated -- eCFR reads "[Reserved]" as of 2026-09-01.

    The section once limited a properly issued invoice to two recipients and
    forbade billing both.  It is no longer in force, so no defect may be raised
    on it: a screen that told a partner an invoice was disputable under a rule
    that no longer exists would be wrong in front of exactly the person we are
    trying to help.  The recipient fields are still ingested and still appear
    in the packet; they simply carry no 541.4 consequence.  Provenance reports
    the section as VACATED rather than silently dropping it.
    """
    assert RULE_541_4["verified"] == "VACATED"
    return []


def _check_closure_accrual(rec: InvoiceRecord) -> list[Defect]:
    """Charges accrued on days the terminal/port was closed.

    Part 541 does not itself void these; the ground sits in the Commission's
    interpretive rule, 46 CFR 545.5, now retrieved verbatim.  Terminal closure
    is NOT one of 545.5's enumerated factors -- it reaches the analysis through
    the general incentive principle at 545.5(c)(1) and the non-preclusion
    clause at 545.5(f), and the finding says so.  DISPUTABLE, never UNPAYABLE:
    it is an argument about reasonableness, not a defect on the face of the
    invoice.
    """
    closed = rec.facts.terminal_closed_dates
    if closed is None:
        closed = rec.closure_dates
    if not closed or not rec.charged_dates:
        return []
    overlap = sorted(set(rec.charged_dates) & set(closed))
    if not overlap:
        return []
    per_day = rec.daily_rate
    amount = (per_day * len(overlap)) if per_day is not None else None
    return [
        Defect(
            code="ACCRUAL_DURING_CLOSURE",
            cite=f"{CLOSURE_FACTOR.cite} (Terminal closure); cf. 46 CFR 541.6(e)(2)",
            rule_text=CLOSURE_FACTOR.text,
            consequence=Consequence.DISPUTABLE,
            summary=(
                f"{len(overlap)} charged day(s) fall on dates the terminal or port "
                f"was closed or the container was not retrievable"
                + (f" ({rec.closure_reason})" if rec.closure_reason else "")
                + f": {', '.join(d.isoformat() for d in overlap)}. The invoice "
                f"nonetheless certifies that the billing party's performance did "
                f"not cause or contribute to the charges (46 CFR 541.6(e)(2)). "
                f"Terminal closure is not an enumerated 545.5 factor; it is "
                f"raised under the general incentive principle at 545.5(c)(1) "
                f"together with the non-preclusion clause at 545.5(f)."
                + (
                    f" Amount attributable at the stated daily rate: ${amount}."
                    if amount is not None
                    else " No daily rate is stated, so the attributable amount cannot be computed."
                )
            ),
            math=(
                f"charged_days={len(rec.charged_dates)}, closure_days={len(rec.closure_dates)}, "
                f"overlap={len(overlap)}"
                + (f", daily_rate={per_day} -> {amount}" if amount is not None else "")
            ),
            verified=rules.VERBATIM,
        )
    ]


def _check_arithmetic(rec: InvoiceRecord) -> list[Defect]:
    """Total vs rate x charged days -- 541.6(c) requires the amount be
    readily ascertainable from the stated rate."""
    if rec.daily_rate is None or not rec.charged_dates:
        return []
    expected = rec.daily_rate * len(rec.charged_dates)
    if expected == rec.total_amount:
        return []
    el = rules.ELEMENTS_BY_KEY["541.6(c)(1)"]
    return [
        Defect(
            code="AMOUNT_NOT_ASCERTAINABLE",
            cite="46 CFR 541.6(c)",
            rule_text=rules.GROUP_LEADS["rate"] + " " + el.text,
            consequence=Consequence.DISPUTABLE,
            summary=(
                f"The total billed (${rec.total_amount}) does not equal the stated "
                f"daily rate (${rec.daily_rate}) times the number of charged days "
                f"({len(rec.charged_dates)}) = ${expected}. The amount due is not "
                f"readily ascertainable from the invoice as required."
            ),
            math=(
                f"{rec.daily_rate} x {len(rec.charged_dates)} = {expected} "
                f"!= stated total {rec.total_amount} "
                f"(delta {rec.total_amount - expected})"
            ),
        )
    ]


def _factor_defect(
    factor: ReasonablenessFactor,
    rec: InvoiceRecord,
    overlap: list[date] | None,
    why: str,
) -> Defect:
    per_day = rec.daily_rate
    amount = (per_day * len(overlap)) if (per_day is not None and overlap) else None
    enum = (
        "This is an enumerated factor of 46 CFR 545.5."
        if factor.enumerated
        else (
            "This factor is NOT enumerated in 46 CFR 545.5. It is raised under "
            "the general incentive principle at 545.5(c)(1) together with the "
            "non-preclusion clause at 545.5(f)."
        )
    )
    if overlap is None:
        math = f"factor={factor.key}, asserted=True"
    else:
        math = (
            f"factor={factor.key}, asserted_days={len(overlap)}, "
            f"overlap_with_charged={[d.isoformat() for d in overlap]}"
            + (f", daily_rate={per_day} -> {amount}" if amount is not None else "")
        )
    return Defect(
        code="UNREASONABLE_545_5",
        cite=f"{factor.cite} ({factor.label})",
        rule_text=factor.text,
        consequence=Consequence.DISPUTABLE,
        summary=(
            f"{factor.label}: {why} {enum} Under {RULE_545_5['cite']} the "
            f"Commission weighs whether the charge served its intended purpose "
            f"as a financial incentive; the billed party asserts it did not."
            + (
                f" Amount attributable at the stated daily rate: ${amount}."
                if amount is not None
                else ""
            )
        ),
        math=math,
        verified=factor.verified,
    )


def _check_545_5_factors(rec: InvoiceRecord) -> list[Defect]:
    """46 CFR 545.5 reasonableness factors, screened from CLIENT-SUPPLIED facts.

    A factor fires only on an affirmative assertion.  An unknown fact produces
    an :class:`EvidenceGap` (see :func:`_evidence_gaps`), never a defect.
    """
    out: list[Defect] = []
    facts = rec.facts
    charged = set(rec.charged_dates)

    for factor in FACTORS_545_5:
        value = getattr(facts, factor.fact_field)
        if value is None:  # not asserted -- never assumed
            continue
        if factor.fact_field == "notice_of_availability_given":
            if value is False:
                out.append(
                    _factor_defect(
                        factor,
                        rec,
                        None,
                        "The billed party states it received no notice that the "
                        "cargo was available for retrieval.",
                    )
                )
            continue
        if factor.fact_field == "charge_could_not_incentivise":
            if value is True:
                out.append(
                    _factor_defect(
                        factor,
                        rec,
                        None,
                        "The billed party states that no act of its own could "
                        "have avoided or shortened the charge on the days billed.",
                    )
                )
            continue
        if not value:
            continue
        overlap = sorted(set(value) & charged) if charged else sorted(value)
        if not overlap:
            continue
        out.append(
            _factor_defect(
                factor,
                rec,
                overlap,
                f"{len(overlap)} charged day(s) fall on dates the billed party "
                f"states this factor applied: "
                f"{', '.join(d.isoformat() for d in overlap)}.",
            )
        )
    return out


def _evidence_gaps(rec: InvoiceRecord) -> list[EvidenceGap]:
    """Every 545.5 factor whose underlying fact the client has not supplied."""
    gaps: list[EvidenceGap] = []
    all_factors = list(FACTORS_545_5)
    if rec.facts.terminal_closed_dates is None and not rec.closure_dates:
        all_factors.append(CLOSURE_FACTOR)
    for factor in all_factors:
        if getattr(rec.facts, factor.fact_field) is None:
            gaps.append(
                EvidenceGap(
                    factor_key=factor.key,
                    cite=factor.cite,
                    label=factor.label,
                    fact_field=factor.fact_field,
                    evidence=factor.evidence,
                )
            )
    return gaps


CHECKS = (
    _check_issuance_clock,
    _check_required_elements,
    _check_dispute_window,
    _check_billing_recipient,
    _check_closure_accrual,
    _check_545_5_factors,
    _check_arithmetic,
)


def _deadlines(rec: InvoiceRecord) -> dict[str, date]:
    out: dict[str, date] = {}
    if rec.billing_party_type == "nvocc" and rec.upstream_invoice_issue_date:
        out["invoice_due_by_541_7b"] = rec.upstream_invoice_issue_date + timedelta(
            days=rules.INVOICE_WINDOW_DAYS
        )
    out["invoice_due_by_541_7a"] = rec.charge_last_incurred + timedelta(
        days=rules.INVOICE_WINDOW_DAYS
    )
    out["mitigation_request_due_by_541_8a"] = rec.invoice_issue_date + timedelta(
        days=rules.MITIGATION_REQUEST_DAYS
    )
    return out


def screen_invoice(rec: InvoiceRecord) -> ScreenResult:
    """Return every defect found in ``rec``, with citation and arithmetic."""
    result = ScreenResult(record=rec, deadlines=_deadlines(rec))
    for check in CHECKS:
        result.defects.extend(check(rec))
    result.evidence_needed = _evidence_gaps(rec)
    return result


def screen_all(records: Iterable[InvoiceRecord]) -> list[ScreenResult]:
    return [screen_invoice(r) for r in records]


def resolution_deadline(request_received: date) -> date:
    """46 CFR 541.8(b): billing party must attempt resolution within 30 days."""
    return as_date(request_received) + timedelta(days=rules.MITIGATION_RESOLUTION_DAYS)
