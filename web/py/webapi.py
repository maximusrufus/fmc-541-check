"""Browser adapter for the demurragedesk screening package.

This module is the ONLY translation layer between the web form and the rules.
It contains no rule, no citation, no day count and no letter text of its own:
every verdict, every quotation and every piece of arithmetic below comes out of
``demurragedesk.screen`` / ``demurragedesk.rules`` / ``demurragedesk.packet``,
which are the same modules the CLI and the 61 pytest tests exercise.

It ships inside the same zip as the package and runs under Pyodide in the
browser, so the page cannot drift from the Python: there is no second
implementation to drift from.

Three honesty rails are implemented HERE because they are properties of the
*form*, not of the regulation:

1. **Unsure is not absent.** A 46 CFR 541.6 element the user marked "unsure" is
   passed to the screen as PRESENT, so it can never manufacture a defect, and
   is reported separately as "needs your document". Only an element the user
   affirmatively marked absent reaches 541.5.
2. **No unsupplied money is ever asserted.** The amount at issue is echoed only
   when the user actually typed one. We never total, never extrapolate, and
   never estimate a recovery.
3. **Unasserted facts stay unasserted.** A 545.5 fact the user did not answer
   stays ``None``, which the package already renders as an EvidenceGap rather
   than a ground.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from demurragedesk import packet, rules
from demurragedesk.ingest import DEFAULT_COLUMN_MAP, _record_from_row
from demurragedesk.rules import REQUIRED_ELEMENTS
from demurragedesk.screen import DisputeFacts, InvoiceRecord, as_date, screen_invoice

__all__ = [
    "element_catalog",
    "fact_catalog",
    "screen_payload",
    "screen_csv",
    "provenance",
]

PRESENT, ABSENT, UNSURE = "present", "absent", "unsure"

#: Verdict vocabulary. Exactly three, and the page renders no other.
UNPAYABLE = "UNPAYABLE"
DISPUTABLE = "DISPUTABLE"
NO_DEFECT = "NO DEFECT FOUND"

#: The standing limit of a face-of-document screen. Stated on every result.
SCOPE_NOTE = (
    "This checks the FACE OF THE INVOICE only. It cannot verify that the free "
    "time, the daily rate or the tariff/contract rule stated on the invoice "
    "match your service contract, the terminal schedule or the carrier's filed "
    "tariff - that comparison needs your contract and the operative tariff, and "
    "it is where most substantive overcharges hide. An element that is present "
    "but wrong will pass this screen."
)

SELF_HELP_NOTE = (
    "You may act on this yourself, for free. 46 CFR 541.8 gives you at least 30 "
    "calendar days from the invoice issue date to request mitigation, refund or "
    "waiver, and no licence, lawyer or filing fee is required to send the "
    "request below to the billing party."
)


def element_catalog(direction: str = "import") -> list[dict]:
    """Every 46 CFR 541.6 element the form must ask about, from the rule table."""
    return [
        {
            "key": el.key,
            "cite": el.cite,
            "group": el.group,
            "group_lead": rules.GROUP_LEADS[el.group],
            "text": el.text,
            "field_name": el.field_name,
        }
        for el in REQUIRED_ELEMENTS
        if el.applicable(direction)
    ]


def fact_catalog() -> list[dict]:
    """Every 46 CFR 545.5 factor, with what the user must be able to evidence."""
    factors = list(rules.FACTORS_545_5) + [rules.CLOSURE_FACTOR]
    return [
        {
            "key": f.key,
            "cite": f.cite,
            "label": f.label,
            "fact_field": f.fact_field,
            "evidence": f.evidence,
            "enumerated": f.enumerated,
            "kind": "bool" if f.fact_field in _BOOL_FACTS else "dates",
        }
        for f in factors
    ]


_BOOL_FACTS = {"notice_of_availability_given", "charge_could_not_incentivise"}


# ---------------------------------------------------------------------------
# Coercion helpers -- every one of them refuses to invent a value
# ---------------------------------------------------------------------------


def _opt_date(value):
    if value in (None, "", False):
        return None
    return as_date(value)


def _opt_money(value):
    if value in (None, "", False):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{value!r} is not an amount")


def _opt_int(value):
    if value in (None, "", False):
        return None
    return int(Decimal(str(value).strip()))


def _date_list(value):
    if value in (None, "", False):
        return ()
    if isinstance(value, str):
        parts = [
            p.strip() for p in value.replace(";", ",").replace("|", ",").split(",")
        ]
        value = [p for p in parts if p]
    return tuple(as_date(d) for d in value)


def _facts_from(payload) -> tuple[DisputeFacts, list[str]]:
    """Build DisputeFacts. An unanswered question stays None -- never False."""
    raw = payload.get("facts") or {}
    kwargs = {}
    asserted = []
    for f in list(rules.FACTORS_545_5) + [rules.CLOSURE_FACTOR]:
        if f.fact_field not in raw:
            continue
        value = raw[f.fact_field]
        if value is None or value == "" or value == "unsure":
            continue  # NOT ASSERTED -- stays None, becomes an EvidenceGap
        if f.fact_field in _BOOL_FACTS:
            if value in ("yes", "true", True):
                kwargs[f.fact_field] = True
            elif value in ("no", "false", False):
                kwargs[f.fact_field] = False
            else:
                continue
        else:
            kwargs[f.fact_field] = _date_list(value)
        asserted.append(f.fact_field)
    return DisputeFacts(**kwargs), asserted


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------


def _record_from_payload(payload) -> tuple[InvoiceRecord, list[dict]]:
    direction = (payload.get("direction") or "import").lower()
    elements = payload.get("elements") or {}

    present = set()
    unsure = []
    for el in REQUIRED_ELEMENTS:
        if not el.applicable(direction):
            continue
        state = (elements.get(el.key) or UNSURE).lower()
        if state == PRESENT:
            present.add(el.key)
        elif state == UNSURE:
            # RAIL 1: unsure can never produce a defect. Treated as present for
            # the screen, and surfaced to the user as a document question.
            present.add(el.key)
            unsure.append(
                {"key": el.key, "cite": el.cite, "text": el.text, "group": el.group}
            )
        # state == ABSENT -> deliberately not added; 541.5 does the rest.

    facts, _ = _facts_from(payload)

    kwargs = dict(
        invoice_id=(payload.get("invoice_id") or "(unnumbered)"),
        invoice_issue_date=as_date(payload["invoice_issue_date"]),
        charge_last_incurred=as_date(payload["charge_last_incurred"]),
        charge_type=(payload.get("charge_type") or "demurrage").lower(),
        direction=direction,
        billing_party=payload.get("billing_party") or "",
        billing_party_type=(
            payload.get("billing_party_type") or "ocean_common_carrier"
        ).lower(),
        billed_party=payload.get("billed_party") or "",
        billed_party_role=(
            payload.get("billed_party_role") or "contracting_party"
        ).lower(),
        container_number=payload.get("container_number") or "",
        bill_of_lading=payload.get("bill_of_lading") or "",
        port_of_discharge=payload.get("port_of_discharge") or "",
        charged_dates=_date_list(payload.get("charged_dates")),
        closure_dates=_date_list(payload.get("closure_dates")),
        closure_reason=payload.get("closure_reason") or "",
        present_fields=frozenset(present),
        facts=facts,
        source="web",
    )
    total = _opt_money(payload.get("total_amount"))
    kwargs["total_amount"] = total if total is not None else Decimal("0")
    for name, fn in (
        ("charge_first_incurred", _opt_date),
        ("upstream_invoice_issue_date", _opt_date),
        ("daily_rate", _opt_money),
        ("free_time_days", _opt_int),
        ("stated_dispute_window_days", _opt_int),
    ):
        value = fn(payload.get(name))
        if value is not None:
            kwargs[name] = value
    if payload.get("also_invoiced_consignee") in (True, "yes", "true"):
        kwargs["also_invoiced_consignee"] = True
    return InvoiceRecord(**kwargs), unsure


def _verdict(result) -> str:
    if result.unpayable:
        return UNPAYABLE
    if result.disputable_defects:
        return DISPUTABLE
    return NO_DEFECT


def _result_dict(result, unsure, payload) -> dict:
    rec = result.record
    user_supplied_amount = str(payload.get("total_amount") or "").strip() != ""
    today = _opt_date(payload.get("today")) or date.today()

    parties = packet.PacketParty(
        billed_party=payload.get("billed_party") or "[billed party]",
        billed_party_contact=payload.get("billed_party_contact") or "",
        billing_party=payload.get("billing_party") or rec.billing_party or "",
        billing_party_contact=payload.get("billing_party_contact") or "",
    )

    out = {
        "invoice_id": rec.invoice_id,
        "verdict": _verdict(result),
        "unpayable": result.unpayable,
        "clean": result.clean,
        "defects": [d.as_dict() for d in result.defects],
        "unpayable_defects": [d.as_dict() for d in result.unpayable_defects],
        "disputable_defects": [d.as_dict() for d in result.disputable_defects],
        "evidence_needed": [g.as_dict() for g in result.evidence_needed],
        "needs_your_document": unsure,
        "deadlines": {k: v.isoformat() for k, v in result.deadlines.items()},
        # RAIL 2: money is echoed, never asserted.
        "amount_supplied_by_user": user_supplied_amount,
        "amount_at_issue": str(result.amount_at_issue)
        if user_supplied_amount
        else None,
        "amount_note": (
            "You did not supply an invoice amount, so none is shown. This tool "
            "never estimates what you might recover."
            if not user_supplied_amount
            else "This is the amount YOU entered for this invoice, echoed back. "
            "It is not an estimate of what you will recover."
        ),
        "letter": packet.mitigation_letter(result, parties, today),
        "scope_note": SCOPE_NOTE,
        "self_help_note": SELF_HELP_NOTE,
    }
    return out


def screen_payload(payload) -> dict:
    """Screen one invoice described by the web form."""
    if hasattr(payload, "to_py"):  # a JsProxy handed straight from the worker
        payload = payload.to_py()
    record, unsure = _record_from_payload(payload)
    return _result_dict(screen_invoice(record), unsure, payload)


def screen_csv(text, today=None) -> dict:
    """Screen many invoices from a CSV export, using the package's own ingest.

    Column spellings come from ``demurragedesk.ingest.DEFAULT_COLUMN_MAP``; a
    column that is absent leaves its 541.6 element absent, which is the ingest
    module's documented doctrine (presence is evidence, absence is a finding).
    """
    if hasattr(text, "to_py"):
        text = text.to_py()
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    errors = []
    for i, row in enumerate(rows, 2):  # header is line 1
        try:
            record = _record_from_row(row, DEFAULT_COLUMN_MAP)
        except Exception as exc:  # a row we cannot screen is reported, never guessed
            errors.append({"line": i, "error": str(exc)})
            continue
        payload = {
            "total_amount": row.get("total_amount") or row.get("amount") or "",
            "billed_party": record.billed_party,
            "billing_party": record.billing_party,
            "today": today,
        }
        out.append(_result_dict(screen_invoice(record), [], payload))
    counts = {UNPAYABLE: 0, DISPUTABLE: 0, NO_DEFECT: 0}
    for r in out:
        counts[r["verdict"]] += 1
    return {
        "results": out,
        "errors": errors,
        "counts": counts,
        "scope_note": SCOPE_NOTE,
        "self_help_note": SELF_HELP_NOTE,
    }


def provenance() -> dict:
    return rules.provenance()
