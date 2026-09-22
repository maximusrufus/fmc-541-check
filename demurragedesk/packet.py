"""Generate the two client deliverables.

(a) A 46 CFR 541.8 fee mitigation / refund / waiver request letter, addressed
    to the billing party.
(b) An FMC charge-complaint information packet under 46 U.S.C. 41310.

Both are populated from the screen result, quote the exact rule, name the
specific defect, and open with a factual cover summary.  Both carry the
required standing-and-scope line.

Nothing here files, sends, or submits anything.  The output is a document the
billed party (or its authorised representative) reviews and sends itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import rules
from .rules import (
    CHARGE_COMPLAINT_GUIDANCE,
    CLOCKS,
    FORMAL_COMPLAINT_502_62,
    RULE_41310,
    SMALL_CLAIMS_502_S,
    Consequence,
)
from .screen import ScreenResult

__all__ = [
    "PacketParty",
    "mitigation_letter",
    "fmc_complaint_packet",
    "write_packet",
    "write_pdf",
    "DISCLAIMER",
    "UNPAYABLE_LEAD",
    "DISPUTABLE_LEAD",
]


DISCLAIMER = (
    "This document is prepared for the billed party (or its authorised "
    "representative) named above. It is not legal advice and does not create "
    "an attorney-client relationship. It states the preparer's reading of the "
    "cited regulations against the invoice as received; the billed party is "
    "responsible for reviewing it for factual accuracy before sending it."
)


#: The separation that matters commercially: Part A stands on the document
#: alone; Part B needs facts. Part B must never dilute Part A.
UNPAYABLE_LEAD = (
    "Each item in this Part is a billing defect on the FACE OF THE INVOICE "
    "under 46 CFR part 541. It depends on no fact outside the document, and "
    "the regulation itself provides that the billed party is not required to "
    "pay the charge. This Part does not depend on Part B, and nothing in "
    "Part B qualifies it."
)

DISPUTABLE_LEAD = (
    "Each item in this Part is an argument that the charge was UNREASONABLE "
    "under 46 CFR 545.5 or a procedural objection under 46 CFR part 541. It "
    "does NOT make the charge unpayable on the face of the invoice, and it "
    "depends on facts the billed party must evidence. It is raised in the "
    "alternative and IN ADDITION TO Part A, never in substitution for it."
)


@dataclass
class PacketParty:
    """Who the documents are from and to."""

    billed_party: str
    billed_party_contact: str = ""
    preparer: str = ""
    preparer_role: str = "authorised representative of the billed party"
    billing_party: str = ""
    billing_party_contact: str = ""


def _hdr(title: str) -> str:
    return f"{title}\n{'=' * len(title)}\n"


def _cover_summary(result: ScreenResult) -> str:
    rec = result.record
    unpayable = [d for d in result.defects if d.consequence is Consequence.UNPAYABLE]
    disputable = [d for d in result.defects if d.consequence is Consequence.DISPUTABLE]
    lines = [
        "FACTUAL COVER SUMMARY",
        "---------------------",
        f"Invoice:            {rec.invoice_id}",
        f"Billing party:      {rec.billing_party or '(not stated on invoice)'}"
        f"  [{rec.billing_party_type}]",
        f"Billed party:       {rec.billed_party or '(not stated on invoice)'}",
        f"Charge type:        {rec.charge_type} ({rec.direction})",
        f"Container:          {rec.container_number or '(not stated on invoice)'}",
        f"Bill of lading:     {rec.bill_of_lading or '(not stated on invoice)'}",
        f"Charge last incurred: {rec.charge_last_incurred.isoformat()}",
        f"Invoice issued:       {rec.invoice_issue_date.isoformat()}",
        f"Amount invoiced:      ${rec.total_amount}",
        "",
        f"Defects identified: {len(result.substantive_defects)} "
        f"({len(unpayable)} eliminating the obligation to pay, "
        f"{len(disputable)} supporting mitigation, refund, or waiver).",
        f"  UNPAYABLE (46 CFR part 541, face of the document): {len(unpayable)}",
        f"  DISPUTABLE (46 CFR 545.5 reasonableness, needs facts): {len(disputable)}",
    ]
    if unpayable:
        lines.append(
            "Because at least one defect falls under 46 CFR 541.5 or 46 CFR "
            "541.7, the billed party is not required to pay the charge."
        )
    if result.evidence_needed:
        lines.append(
            f"Facts NOT ASSERTED (needs client evidence): "
            f"{len(result.evidence_needed)} 46 CFR 545.5 factor(s). These are "
            f"neither alleged nor waived below."
        )
    if rec.unresolved_fields:
        lines.append(
            "Fields the preparer could not locate on the invoice document and "
            "did not infer: " + ", ".join(rec.unresolved_fields) + "."
        )
    if rec.source == "ocr":
        lines.append(
            "SOURCE: this record was extracted from a scanned (image) PDF by "
            "OCR, not read from machine text. Every field above is an OCR "
            "read, not a verified transcription -- an OCR misread of a date "
            "or amount changes whether a charge is payable. Before relying on "
            "this packet, the billed party must check every field above "
            "against the original scanned invoice."
        )
    lines.append(
        "Deadlines: "
        + "; ".join(f"{k} = {v.isoformat()}" for k, v in result.deadlines.items())
        + "."
    )
    return "\n".join(lines)


def _render_defects(defects, start: int = 1) -> str:
    out: list[str] = []
    for i, d in enumerate(defects, start):
        out.append(f"{i}. {d.cite} -- {d.consequence.value.upper()}")
        out.append(f'   Rule text: "{d.rule_text}"')
        out.append(f"   Defect:    {d.summary}")
        if d.math:
            out.append(f"   Basis:     {d.math}")
        if d.verified == rules.UNVERIFIED:
            out.append(
                "   NOTE:      One authority behind this item was not "
                "retrieved verbatim by the preparer and is not quoted. "
                "Verify before relying on it."
            )
        out.append("")
    return "\n".join(out)


def _grounds_block(result: ScreenResult) -> str:
    """Two clearly separated Parts: UNPAYABLE first, DISPUTABLE second."""
    if not result.substantive_defects:
        return "No defects identified.\n"
    unpayable = result.unpayable_defects
    disputable = result.disputable_defects
    out: list[str] = []
    out.append(
        "PART A -- CHARGE NOT PAYABLE ON THE FACE OF THE INVOICE (46 CFR part 541)"
    )
    out.append("-" * 72)
    if unpayable:
        out.append(UNPAYABLE_LEAD)
        out.append("")
        out.append(_render_defects(unpayable))
    else:
        out.append(
            "No 46 CFR part 541 billing defect was identified on the face of "
            "the invoice. The billed party does NOT contend the charge is "
            "unpayable on its face."
        )
        out.append("")
    out.append(
        "PART B -- CHARGE DISPUTABLE AS UNREASONABLE (46 CFR 545.5) -- REQUIRES FACTS"
    )
    out.append("-" * 72)
    if disputable:
        out.append(DISPUTABLE_LEAD)
        out.append("")
        out.append(_render_defects(disputable, start=len(unpayable) + 1))
    else:
        out.append("No reasonableness ground is asserted on the facts supplied.")
        out.append("")
    return "\n".join(out)


def _evidence_block(result: ScreenResult) -> str:
    """Facts we do NOT have. Never assumed either way."""
    if not result.evidence_needed:
        return ""
    out = [
        "FACTS NOT ASSERTED -- NEEDS CLIENT EVIDENCE",
        "-------------------------------------------",
        "The following 46 CFR 545.5 factors were NOT screened because the "
        "billed party has not supplied the underlying facts. They are neither "
        "alleged nor waived. Supplying the evidence listed may add grounds to "
        "Part B; it cannot affect Part A.",
        "",
    ]
    for g in result.evidence_needed:
        out.append(f"  * {g.label} ({g.cite}) -- {g.state}")
        out.append(f"    Needed: {g.evidence}")
    out.append("")
    return "\n".join(out)


def _complaint_checklist(result: ScreenResult) -> str:
    """Aligned to the FMC's own charge-complaint guidance and 46 CFR part 502."""
    g = CHARGE_COMPLAINT_GUIDANCE
    out = [
        "WHAT A CHARGE COMPLAINT MUST CONTAIN",
        "------------------------------------",
        f"Per {g['source']}",
        f"Who may file: {g['who']}.",
        f"Scope: {g['scope_note']}",
        "A submission must include:",
    ]
    for i, item in enumerate(g["required"], 1):
        out.append(f"  {i}. {item}")
    out += [
        f"Submission: {g['submission']}",
        "",
        "ATTACHMENTS THE SUBMITTING PARTY SHOULD ENCLOSE",
        "-----------------------------------------------",
        "  1. The invoice as received (complete, all pages) -- the required "
        "supporting documentation.",
        "  2. The bill of lading.",
        "  3. Proof of payment, if any amount was paid.",
        "  4. Any prior 46 CFR 541.8 request and the billing party's response.",
        "  5. For each Part B ground, the evidence supporting the asserted "
        "fact (see the factor list above).",
        "",
        "IF THE COMMISSION'S INFORMAL CHARGE-COMPLAINT ROUTE DOES NOT RESOLVE IT",
        "----------------------------------------------------------------------",
        f"Small claims -- {SMALL_CLAIMS_502_S['cite']}: "
        f'"{SMALL_CLAIMS_502_S["threshold"]}"',
        f'  Limitation: "{SMALL_CLAIMS_502_S["limitation"]}"',
        f'  Form: "{SMALL_CLAIMS_502_S["form"]}"  {SMALL_CLAIMS_502_S["fee"]}',
        f"Formal complaint -- {FORMAL_COMPLAINT_502_62['cite']}: "
        f"{FORMAL_COMPLAINT_502_62['lead']}",
    ]
    for i, item in enumerate(FORMAL_COMPLAINT_502_62["contents"], 1):
        out.append(f"  ({i}) {item}")
    out += [
        f"  {FORMAL_COMPLAINT_502_62['reparation']}",
        f"  {FORMAL_COMPLAINT_502_62['fee']}",
        "",
    ]
    return "\n".join(out)


def _defect_block(result: ScreenResult, include_informational: bool = False) -> str:
    out: list[str] = []
    defects = result.defects if include_informational else result.substantive_defects
    for i, d in enumerate(defects, 1):
        out.append(f"{i}. {d.cite} -- {d.consequence.value.upper()}")
        out.append(f'   Rule text: "{d.rule_text}"')
        out.append(f"   Defect:    {d.summary}")
        if d.math:
            out.append(f"   Basis:     {d.math}")
        if d.verified == rules.UNVERIFIED:
            out.append(
                "   NOTE:      One authority behind this item was not "
                "retrieved verbatim by the preparer and is not quoted. "
                "Verify before relying on it."
            )
        out.append("")
    return "\n".join(out) if out else "No defects identified.\n"


# ---------------------------------------------------------------------------
# (a) 541.8 mitigation / refund / waiver request
# ---------------------------------------------------------------------------


def mitigation_letter(
    result: ScreenResult, parties: PacketParty, today: date | None = None
) -> str:
    rec = result.record
    today = today or date.today()
    request_deadline = result.deadlines["mitigation_request_due_by_541_8a"]
    resolve_by = today + timedelta(days=rules.MITIGATION_RESOLUTION_DAYS)
    c8a, c8b = CLOCKS["541.8(a)"], CLOCKS["541.8(b)"]

    paid_or_owed = "refund" if False else "waiver"
    relief = (
        "waiver of the invoiced charge in full"
        if result.unpayable
        else "mitigation or waiver of the invoiced charge"
    )

    parts = [
        _hdr("REQUEST FOR FEE MITIGATION, REFUND, OR WAIVER"),
        f"Date:    {today.isoformat()}",
        f"To:      {parties.billing_party or rec.billing_party or '[billing party]'}"
        + (
            f"  ({parties.billing_party_contact})"
            if parties.billing_party_contact
            else ""
        ),
        f"From:    {parties.billed_party}"
        + (
            f"  ({parties.billed_party_contact})"
            if parties.billed_party_contact
            else ""
        ),
        (
            f"Prepared by: {parties.preparer}, {parties.preparer_role}"
            if parties.preparer
            else "Prepared by: the billed party"
        ),
        f"Re:      Invoice {rec.invoice_id} -- container "
        f"{rec.container_number or '[container]'} -- ${rec.total_amount}",
        "",
        "Submitted under 46 CFR 541.8 as a request for mitigation, refund, or "
        "waiver of the charge invoiced above.",
        "",
        _cover_summary(result),
        "",
        "GROUNDS",
        "-------",
        _grounds_block(result),
        _evidence_block(result),
        "RELIEF REQUESTED",
        "----------------",
        f"The billed party requests {relief}.",
    ]
    if result.unpayable:
        parts.append(
            "PART A IS THE PRIMARY GROUND. At least one ground above is one on "
            "which the regulation itself "
            "provides that the billed party is not required to pay the charge "
            "(46 CFR 541.5; 46 CFR 541.7). The request is therefore for waiver "
            "of the charge in full, and for refund of any amount already paid."
        )
    parts += [
        "",
        "APPLICABLE TIMEFRAMES",
        "---------------------",
        f'{c8a.cite}: "{c8a.text}"',
        f"  The invoice issued {rec.invoice_issue_date.isoformat()}; the billed "
        f"party therefore has until at least {request_deadline.isoformat()} to "
        f"make this request. This request is made {today.isoformat()}.",
        "",
        f'{c8b.cite}: "{c8b.text}"',
        f"  A written response is therefore requested by "
        f"{resolve_by.isoformat()}, absent an agreed later date.",
        "",
        "If this request is not resolved within that period, the billed party "
        "may submit information concerning this charge to the Federal Maritime "
        "Commission under 46 U.S.C. 41310.",
        "",
        "DISCLAIMER",
        "----------",
        DISCLAIMER,
    ]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# (b) FMC charge-complaint information packet
# ---------------------------------------------------------------------------


def fmc_complaint_packet(
    result: ScreenResult,
    parties: PacketParty,
    *,
    mitigation_requested_on: date | None = None,
    amount_paid: Decimal | None = None,
    today: date | None = None,
) -> str:
    rec = result.record
    today = today or date.today()

    parts = [
        _hdr("FEDERAL MARITIME COMMISSION -- CHARGE COMPLAINT INFORMATION PACKET"),
        f"Submitted under {RULE_41310['cite']} ({RULE_41310['heading']}).",
        f"Date prepared: {today.isoformat()}",
        f"Submitting party (billed party): {parties.billed_party}"
        + (
            f"  ({parties.billed_party_contact})"
            if parties.billed_party_contact
            else ""
        ),
        (
            f"Prepared by: {parties.preparer}, {parties.preparer_role}"
            if parties.preparer
            else "Prepared by: the billed party"
        ),
        f"Charging party (billing party): "
        f"{parties.billing_party or rec.billing_party or '[billing party]'}"
        f"  [{rec.billing_party_type}]",
        "",
        "STATUTORY BASIS",
        "---------------",
        f'{RULE_41310["cite"]}: "{RULE_41310["text"]}"',
        "",
        _cover_summary(result),
        "",
        "CHARGE AT ISSUE",
        "---------------",
        f"Invoice number:        {rec.invoice_id}",
        f"Invoice issue date:    {rec.invoice_issue_date.isoformat()}",
        f"Date charge last incurred: {rec.charge_last_incurred.isoformat()}",
        f"Container number:      {rec.container_number or '(not stated)'}",
        f"Bill of lading:        {rec.bill_of_lading or '(not stated)'}",
        f"Port of discharge:     {rec.port_of_discharge or '(not stated)'}",
        f"Amount invoiced:       ${rec.total_amount}",
        "Amount paid to date:   "
        + (f"${amount_paid}" if amount_paid is not None else "$0 / not stated"),
        "",
        "ALLEGED NON-COMPLIANCE, BY RULE",
        "-------------------------------",
        _grounds_block(result),
        _evidence_block(result),
        "PRIOR RESOLUTION ATTEMPT",
        "------------------------",
    ]
    if mitigation_requested_on:
        due = mitigation_requested_on + timedelta(days=rules.MITIGATION_RESOLUTION_DAYS)
        parts.append(
            f"A request for fee mitigation, refund, or waiver was submitted to "
            f"the billing party on {mitigation_requested_on.isoformat()} under "
            f"46 CFR 541.8(a). Under 46 CFR 541.8(b) the billing party was "
            f"required to attempt to resolve it by {due.isoformat()}."
        )
    else:
        parts.append(
            "No 46 CFR 541.8 request has been recorded as submitted to the "
            "billing party. The billed party should consider making that "
            "request before or alongside this submission."
        )
    parts += [
        "",
        "RELIEF SOUGHT",
        "-------------",
        "That the Commission investigate the charge and, if it determines the "
        "charge does not comply with applicable law or regulation, order the "
        "refund of charges paid.",
        "",
        _complaint_checklist(result),
        "DISCLAIMER",
        "----------",
        DISCLAIMER,
    ]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_packet(
    result: ScreenResult,
    parties: PacketParty,
    outdir: str | Path,
    *,
    pdf: bool = False,
    today: date | None = None,
) -> list[Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    slug = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in result.record.invoice_id
    )[:48]
    written: list[Path] = []

    docs = {
        f"{slug}_541-8_mitigation_request": mitigation_letter(result, parties, today),
        f"{slug}_FMC_41310_complaint": fmc_complaint_packet(
            result, parties, today=today
        ),
    }
    for name, body in docs.items():
        txt = outdir / f"{name}.txt"
        txt.write_text(body, encoding="utf-8")
        written.append(txt)
        if pdf:
            written.append(write_pdf(body, outdir / f"{name}.pdf"))
    return written


def write_pdf(body: str, path: str | Path) -> Path:
    """Render a monospaced, paginated PDF of ``body`` with reportlab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    path = Path(path)
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    left, top, leading = 0.75 * inch, height - 0.9 * inch, 11.5
    max_chars = 92
    y = top
    c.setFont("Courier", 8.6)
    for raw_line in body.splitlines():
        chunks = [
            raw_line[i : i + max_chars] for i in range(0, len(raw_line), max_chars)
        ] or [""]
        for chunk in chunks:
            if y < 0.9 * inch:
                c.showPage()
                c.setFont("Courier", 8.6)
                y = top
            c.drawString(left, y, chunk)
            y -= leading
    c.save()
    return path
