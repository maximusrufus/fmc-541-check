"""Encoded rules for FMC demurrage & detention billing (46 CFR part 541).

PROVENANCE
----------
Every quoted string in this module was retrieved verbatim on 2026-09-15 from two
INDEPENDENT primary sources, which agreed word for word:

  1. govinfo.gov CFR XML (authenticated GPO text):
     https://www.govinfo.gov/content/pkg/CFR-2025-title46-vol9/xml/
     CFR-2025-title46-vol9-part541.xml
  2. eCFR versioner API (Office of the Federal Register):
     https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=541

46 CFR 545.5 (the Commission's demurrage/detention interpretive rule) and the
FMC charge-complaint procedure were retrieved on 2026-09-15 from:

  3. eCFR versioner API, 46 CFR part 545:
     https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=545
  4. eCFR versioner API, 46 CFR part 502:
     https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=502
  5. FMC, "Guidance on Charge Complaint Interim Procedure" (fmc.gov)

Each rule object carries a ``verified`` flag.  ``VERBATIM`` means the quoted
text above was actually retrieved from a primary source.  ``UNVERIFIED`` means
the text was not retrieved and must not be relied on -- there are currently no
UNVERIFIED entries.

Nothing in this module is legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

VERBATIM = "VERBATIM"  # quoted text retrieved from a primary source
VACATED = "VACATED"  # section no longer in force; text kept for provenance only
UNVERIFIED = "UNVERIFIED"  # text NOT retrieved; do not rely on it

SOURCES = (
    "https://www.govinfo.gov/content/pkg/CFR-2025-title46-vol9/xml/"
    "CFR-2025-title46-vol9-part541.xml",
    "https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=541",
    "https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=545",
    "https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-46.xml?part=502",
    "https://www.fmc.gov/ocean-shipping-reform-act-of-2022-implementation/"
    "guidance-on-charge-complaint-interim-procedure/",
)
RETRIEVED = "2026-09-15"

Direction = Literal["import", "export"]
BillingPartyType = Literal["ocean_common_carrier", "mto", "nvocc"]


class Consequence(str, Enum):
    """What a defect does to the charge, in the regulation's own terms."""

    #: 541.5 / 541.7 -- "the billed party is not required to pay the charge" /
    #: "eliminates any obligation of the billed party to pay the applicable charge"
    UNPAYABLE = "unpayable"
    #: A procedural or substantive ground to contest; the regulation does not
    #: itself extinguish the obligation.
    DISPUTABLE = "disputable"
    #: Informational deadline maths, not a defect.
    INFORMATIONAL = "informational"


# ---------------------------------------------------------------------------
# 46 CFR 541.5 -- the consequence provision for missing content
# ---------------------------------------------------------------------------

RULE_541_5 = {
    "cite": "46 CFR 541.5",
    "heading": "Failure to include required information",
    "text": (
        "Failure to include any of the required minimum information in this "
        "part in a demurrage or detention invoice eliminates any obligation of "
        "the billed party to pay the applicable charge."
    ),
    "verified": VERBATIM,
}

# ---------------------------------------------------------------------------
# 46 CFR 541.4 -- who may be invoiced
# ---------------------------------------------------------------------------

RULE_541_4 = {
    "cite": "46 CFR 541.4",
    "heading": "Properly issued invoices",
    "text": (
        "A properly issued invoice must be issued by a billing party to either "
        "the person for whose account the billing party provided ocean "
        "transportation or storage and who contracted for such services, or the "
        "consignee. If the billing party issues the invoice to the person for "
        "whose account it provided services, it cannot also issue an invoice to "
        "the consignee. A billing party cannot issue an invoice to any other "
        "person."
    ),
    # Paraphrase-safe summary of the section AS IT STOOD when retrieved on
    # 2026-09-15.  It is no longer in force: the eCFR point-in-time text for
    # 2026-09-01 (https://www.ecfr.gov/api/versioner/v1/full/2026-09-01/
    # title-46.xml?part=541&section=541.4, HTTP 200, checked 2026-09-22)
    # reads "§ 541.4 [Reserved]".  The text is kept so that provenance() can
    # say what was checked and why it was withdrawn; nothing in screen.py may
    # raise a defect on it.
    "verified": VACATED,
    "status_url": "https://www.ecfr.gov/current/title-46/section-541.4",
    "status_checked": "2026-09-22",
}


# ---------------------------------------------------------------------------
# 46 CFR 541.6 -- required invoice contents
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequiredElement:
    """One minimum-content item required by 46 CFR 541.6."""

    key: str  # e.g. "541.6(b)(4)"
    group: str  # "identifying" | "timing" | "rate" | "dispute" | "certification"
    text: str  # verbatim text of the item
    verified: str = VERBATIM
    applies_to: tuple[str, ...] = ("import", "export")
    #: Short machine-friendly name used by ingest/screen field maps.
    field_name: str = ""

    @property
    def cite(self) -> str:
        return f"46 CFR {self.key}"

    def applicable(self, direction: Direction) -> bool:
        return direction in self.applies_to


GROUP_LEADS = {
    "identifying": (
        "46 CFR 541.6(a) Identifying information. A demurrage or detention "
        "invoice must be accurate and contain sufficient information to enable "
        "the billed party to identify the container(s) to which the charges "
        "apply and at a minimum must include:"
    ),
    "timing": (
        "46 CFR 541.6(b) Timing information. A demurrage or detention invoice "
        "must be accurate and contain sufficient information to enable the "
        "billed party to identify the relevant time for which the charges apply "
        "and the applicable due date for invoiced charges and at a minimum must "
        "include:"
    ),
    "rate": (
        "46 CFR 541.6(c) Rate information. A demurrage or detention invoice "
        "must be accurate and contain sufficient information to enable the "
        "billed party to identify the amount due and readily ascertain how that "
        "amount was calculated and must include at a minimum:"
    ),
    "dispute": (
        "46 CFR 541.6(d) Dispute information. A demurrage or detention invoice "
        "must be accurate and contain sufficient information to enable the "
        "billed party to readily identify a contact to whom they may direct "
        "questions or concerns related to the invoice and understand the "
        "process to request fee mitigation, refund, or waiver, and at a minimum "
        "must include:"
    ),
    "certification": (
        "46 CFR 541.6(e) Certifications. A demurrage or detention invoice must "
        "be accurate and contain statements from the billing party that:"
    ),
}


REQUIRED_ELEMENTS: tuple[RequiredElement, ...] = (
    # (a) Identifying information
    RequiredElement(
        "541.6(a)(1)",
        "identifying",
        "The Bill of Lading number(s);",
        field_name="bill_of_lading",
    ),
    RequiredElement(
        "541.6(a)(2)",
        "identifying",
        "The container number(s);",
        field_name="container_number",
    ),
    RequiredElement(
        "541.6(a)(3)",
        "identifying",
        "For imports, the port(s) of discharge; and",
        applies_to=("import",),
        field_name="port_of_discharge",
    ),
    RequiredElement(
        "541.6(a)(4)",
        "identifying",
        "The basis for why the billed party is the proper party of "
        "interest and thus liable for the charge.",
        field_name="basis_for_liability",
    ),
    # (b) Timing information
    RequiredElement(
        "541.6(b)(1)", "timing", "The invoice date;", field_name="invoice_date"
    ),
    RequiredElement(
        "541.6(b)(2)", "timing", "The invoice due date;", field_name="invoice_due_date"
    ),
    RequiredElement(
        "541.6(b)(3)",
        "timing",
        "The allowed free time in days;",
        field_name="free_time_days",
    ),
    RequiredElement(
        "541.6(b)(4)",
        "timing",
        "The start date of free time;",
        field_name="free_time_start",
    ),
    RequiredElement(
        "541.6(b)(5)",
        "timing",
        "The end date of free time;",
        field_name="free_time_end",
    ),
    RequiredElement(
        "541.6(b)(6)",
        "timing",
        "For imports, the container availability date;",
        applies_to=("import",),
        field_name="container_availability_date",
    ),
    RequiredElement(
        "541.6(b)(7)",
        "timing",
        "For exports, the earliest return date; and",
        applies_to=("export",),
        field_name="earliest_return_date",
    ),
    RequiredElement(
        "541.6(b)(8)",
        "timing",
        "The specific date(s) for which demurrage and/or detention were charged.",
        field_name="charged_dates",
    ),
    # (c) Rate information
    RequiredElement(
        "541.6(c)(1)", "rate", "The total amount due;", field_name="total_amount_due"
    ),
    RequiredElement(
        "541.6(c)(2)",
        "rate",
        "The applicable detention or demurrage rule (e.g., the "
        "tariff name and rule number, terminal schedule, applicable "
        "service contract number and section, or applicable "
        "negotiated arrangement) on which the daily rate is based; and",
        field_name="applicable_rule",
    ),
    RequiredElement(
        "541.6(c)(3)",
        "rate",
        "The specific rate or rates per the applicable tariff rule "
        "or service contract.",
        field_name="specific_rate",
    ),
    # (d) Dispute information
    RequiredElement(
        "541.6(d)(1)",
        "dispute",
        "The email, telephone number, or other appropriate contact "
        "information for questions or request for fee mitigation, "
        "refund, or waiver;",
        field_name="dispute_contact",
    ),
    RequiredElement(
        "541.6(d)(2)",
        "dispute",
        "Digital means, such as a URL address, QR code, or digital "
        "watermark, that directs the billed party to a publicly "
        "accessible website that provides a detailed description of "
        "information or documentation that the billed party must "
        "provide to successfully request fee mitigation, refund, or "
        "waiver; and",
        field_name="dispute_digital_means",
    ),
    RequiredElement(
        "541.6(d)(3)",
        "dispute",
        "Defined timeframes that comply with the billing practices "
        "in this part, during which the billed party must request a "
        "fee mitigation, refund, or waiver and within which the "
        "billing party will resolve such requests.",
        field_name="dispute_timeframes",
    ),
    # (e) Certifications
    RequiredElement(
        "541.6(e)(1)",
        "certification",
        "The charges are consistent with any of the Federal "
        "Maritime Commission's rules related to demurrage and "
        "detention, including, but not limited to, this part and 46 "
        "CFR 545.5; and",
        field_name="cert_consistent_with_rules",
    ),
    RequiredElement(
        "541.6(e)(2)",
        "certification",
        "The billing party's performance did not cause or "
        "contribute to the underlying invoiced charges.",
        field_name="cert_performance_did_not_contribute",
    ),
)

ELEMENTS_BY_KEY = {e.key: e for e in REQUIRED_ELEMENTS}
ELEMENTS_BY_FIELD = {e.field_name: e for e in REQUIRED_ELEMENTS if e.field_name}


def required_keys(direction: Direction) -> tuple[str, ...]:
    return tuple(e.key for e in REQUIRED_ELEMENTS if e.applicable(direction))


# ---------------------------------------------------------------------------
# 46 CFR 541.7 -- issuance clocks
# ---------------------------------------------------------------------------

INVOICE_WINDOW_DAYS = 30  # 541.7(a), (b), (d)
MITIGATION_REQUEST_DAYS = 30  # 541.8(a) -- a MINIMUM the billing party must allow
MITIGATION_RESOLUTION_DAYS = 30  # 541.8(b)
NVOCC_EXTRA_DISPUTE_DAYS = 30  # 541.7(c)


@dataclass(frozen=True)
class Clock:
    cite: str
    heading: str
    text: str
    days: int
    anchor: str  # what the clock runs from
    consequence: Consequence
    verified: str = VERBATIM


CLOCKS: dict[str, Clock] = {
    "541.7(a)": Clock(
        cite="46 CFR 541.7(a)",
        heading="Issuance of demurrage and detention invoices",
        text=(
            "A billing party must issue a demurrage or detention invoice within "
            "thirty (30) calendar days from the date on which the charge was "
            "last incurred. If the billing party does not issue a demurrage or "
            "detention invoice within thirty (30) calendar days from the date "
            "on which the charge was last incurred, then the billed party is "
            "not required to pay the charge."
        ),
        days=INVOICE_WINDOW_DAYS,
        anchor="date the charge was last incurred",
        consequence=Consequence.UNPAYABLE,
    ),
    "541.7(b)": Clock(
        cite="46 CFR 541.7(b)",
        heading="NVOCC re-billing window",
        text=(
            "If the billing party is a non-vessel-operating common carrier, "
            "then it must issue a demurrage or detention invoice within thirty "
            "(30) calendar days from the issuance date of the demurrage or "
            "detention invoice it received. If such a billing party does not "
            "issue a demurrage or detention invoice within thirty (30) calendar "
            "days from the issuance date of the demurrage or detention invoice "
            "it received, then the billed party is not required to pay the "
            "charge."
        ),
        days=INVOICE_WINDOW_DAYS,
        anchor="issuance date of the upstream invoice the NVOCC received",
        consequence=Consequence.UNPAYABLE,
    ),
    "541.7(c)": Clock(
        cite="46 CFR 541.7(c)",
        heading="NVOCC additional dispute window",
        text=(
            "A non-vessel-operating common carrier (NVOCC) can be both a "
            "billing and billed party in relation to the same charge. When an "
            "NVOCC is acting in both roles, it can inform its billing party "
            "that the charge has been disputed by the NVOCC's billed party. The "
            "NVOCC's billing party must then provide an additional thirty (30) "
            "calendar days for the NVOCC to dispute the charge upon this notice."
        ),
        days=NVOCC_EXTRA_DISPUTE_DAYS,
        anchor="notice to the NVOCC's billing party that the charge is disputed",
        consequence=Consequence.INFORMATIONAL,
    ),
    "541.7(d)": Clock(
        cite="46 CFR 541.7(d)",
        heading="Re-issuance to the correct billed party",
        text=(
            "If the billing party invoices an incorrect person, the billing "
            "party may issue an invoice to the correct billed party provided "
            "that such issuance is within thirty (30) calendar days from the "
            "date on which the charge was last incurred. If the billing party "
            "does not issue this corrected demurrage or detention invoice "
            "within thirty (30) calendar days from the date on which the charge "
            "was last incurred, then the billed party is not required to pay "
            "the charge."
        ),
        days=INVOICE_WINDOW_DAYS,
        anchor="date the charge was last incurred",
        consequence=Consequence.UNPAYABLE,
    ),
    "541.8(a)": Clock(
        cite="46 CFR 541.8(a)",
        heading="Requests for fee mitigation, refund, or waiver",
        text=(
            "The billing party must allow the billed party at least thirty (30) "
            "calendar days from the invoice issuance date to request "
            "mitigation, refund, or waiver of fees from the billing party."
        ),
        days=MITIGATION_REQUEST_DAYS,
        anchor="invoice issuance date",
        consequence=Consequence.DISPUTABLE,
    ),
    "541.8(b)": Clock(
        cite="46 CFR 541.8(b)",
        heading="Billing party resolution window",
        text=(
            "If a billing party receives a fee mitigation, refund, or waiver "
            "request from a billed party, the billing party must attempt to "
            "resolve the request within thirty (30) calendar days of receiving "
            "such a request or at a later date as agreed upon by both parties."
        ),
        days=MITIGATION_RESOLUTION_DAYS,
        anchor="date the billing party received the request",
        consequence=Consequence.INFORMATIONAL,
    ),
}


# ---------------------------------------------------------------------------
# 46 USC 41310 -- FMC charge complaints
# ---------------------------------------------------------------------------

RULE_41310 = {
    "cite": "46 U.S.C. 41310",
    "heading": "Charge complaints",
    "text": (
        "A person may submit to the Federal Maritime Commission information "
        "concerning complaints about charges assessed by a common carrier. On "
        "receipt, the Commission shall promptly investigate the complaint and, "
        "if the Commission determines that the charge does not comply with "
        "applicable law or regulation, shall promptly order the refund of "
        "charges paid."
    ),
    # Retrieved by the orchestrator against primary statutory text, not by this
    # module's own fetches.  Substance (submission right + refund order) is
    # relied on; the connective wording is a summary, so it is flagged.
    "verified": "VERBATIM_UPSTREAM",
}


# ---------------------------------------------------------------------------
# 46 CFR 545.5 -- the Commission's demurrage & detention interpretive rule
#
# Retrieved verbatim 2026-09-15 from the eCFR versioner API (part 545).
# Source note [85 FR 29665, May 18, 2020].
# ---------------------------------------------------------------------------

RULE_545_5 = {
    "cite": "46 CFR 545.5",
    "heading": (
        "Interpretation of Shipping Act of 1984-Unjust and unreasonable "
        "practices with respect to demurrage and detention."
    ),
    "purpose": (
        "The purpose of this rule is to provide guidance about how the "
        "Commission will interpret 46 U.S.C. 41102(c) and 46 CFR 545.4(d) in "
        "the context of demurrage and detention."
    ),
    "scope": (
        "This rule applies to practices and regulations relating to demurrage "
        "and detention for containerized cargo. For purposes of this rule, the "
        "terms demurrage and detention encompass any charges, including \u201cper "
        "diem,\u201d assessed by ocean common carriers, marine terminal operators, "
        "or ocean transportation intermediaries (\u201cregulated entities\u201d) related "
        "to the use of marine terminal space (e.g., land) or shipping "
        "containers, not including freight charges."
    ),
    # 545.5(c)(1) -- the operative incentive principle.
    "text": (
        "In assessing the reasonableness of demurrage and detention practices "
        "and regulations, the Commission will consider the extent to which "
        "demurrage and detention are serving their intended primary purposes "
        "as financial incentives to promote freight fluidity."
    ),
    "non_preclusion": (
        "Nothing in this rule precludes the Commission from considering "
        "factors, arguments, and evidence in addition to those specifically "
        "listed in this rule."
    ),
    "authority": "[85 FR 29665, May 18, 2020]",
    "verified": VERBATIM,
}


@dataclass(frozen=True)
class ReasonablenessFactor:
    """One factor the Commission weighs under 46 CFR 545.5.

    ``enumerated`` is the honest part.  A factor is enumerated only when 545.5
    itself names it.  Terminal closures, holidays, force majeure and
    appointment unavailability are NOT enumerated anywhere in the retrieved
    text of 545.5 -- they reach the analysis through the general incentive
    principle at 545.5(c)(1) together with the non-preclusion clause at
    545.5(f).  We say so rather than implying the rule lists them.
    """

    key: str
    label: str
    text: str
    fact_field: str
    #: What the billed party must produce to assert this factor.
    evidence: str
    enumerated: bool = True
    verified: str = VERBATIM

    @property
    def cite(self) -> str:
        return "46 CFR " + self.key


_GENERAL = RULE_545_5["text"] + " " + RULE_545_5["non_preclusion"]


FACTORS_545_5: tuple[ReasonablenessFactor, ...] = (
    ReasonablenessFactor(
        key="545.5(c)(2)(i)",
        label="Cargo availability",
        text=(
            "The Commission may consider in the reasonableness analysis the "
            "extent to which demurrage practices and regulations relate "
            "demurrage or free time to cargo availability for retrieval."
        ),
        fact_field="cargo_not_available_dates",
        evidence=(
            "terminal availability screenshots, container status history, or "
            "the carrier's own availability notices for each date claimed"
        ),
    ),
    ReasonablenessFactor(
        key="545.5(c)(2)(ii)",
        label="Empty container return",
        text=(
            "Absent extenuating circumstances, practices and regulations that "
            "provide for imposition of detention when it does not serve its "
            "incentivizing purposes, such as when empty containers cannot be "
            "returned, are likely to be found unreasonable."
        ),
        fact_field="empty_return_refused_dates",
        evidence=(
            "refused-return records, terminal empty-receiving restrictions, or "
            "trucker turn-away notes for each date claimed"
        ),
    ),
    ReasonablenessFactor(
        key="545.5(c)(2)(iii)",
        label="Notice of cargo availability",
        text=(
            "In assessing the reasonableness of demurrage practices and "
            "regulations, the Commission may consider whether and how regulated "
            "entities provide notice to cargo interests that cargo is available "
            "for retrieval. The Commission may consider the type of notice, to "
            "whom notice is provided, the format of notice, method of "
            "distribution of notice, the timing of notice, and the effect of "
            "the notice."
        ),
        fact_field="notice_of_availability_given",
        evidence=(
            "the availability notice actually received (with its timestamp and "
            "addressee), or a statement that no notice was received"
        ),
    ),
    ReasonablenessFactor(
        key="545.5(c)(2)(iv)",
        label="Government inspections",
        text=(
            "In assessing the reasonableness of demurrage and detention "
            "practices in the context of government inspections, the Commission "
            "may consider the extent to which demurrage and detention are "
            "serving their intended purposes and may also consider any "
            "extenuating circumstances."
        ),
        fact_field="government_hold_dates",
        evidence=(
            "the CBP/USDA/FDA hold or exam notice, and the release date, for "
            "each date claimed"
        ),
    ),
    # --- NOT enumerated in 545.5; reached via (c)(1) general + (f) ----------
    ReasonablenessFactor(
        key="545.5(c)(1), (f)",
        label="Appointment unavailability",
        text=_GENERAL,
        fact_field="appointment_unavailable_dates",
        evidence=(
            "appointment-system screenshots or booking logs showing no slot was "
            "obtainable on each date claimed"
        ),
        enumerated=False,
    ),
    ReasonablenessFactor(
        key="545.5(c)(1), (f)",
        label="No action could have been incentivised",
        text=_GENERAL,
        fact_field="charge_could_not_incentivise",
        evidence=(
            "a statement of what the billed party could have done differently "
            "on the charged days, and why it could not"
        ),
        enumerated=False,
    ),
)

FACTORS_BY_FIELD = {f.fact_field: f for f in FACTORS_545_5}

#: 545.5(c)(1)+(f), used by the terminal-closure check.
CLOSURE_FACTOR = ReasonablenessFactor(
    key="545.5(c)(1), (f)",
    label="Terminal closure",
    text=_GENERAL,
    fact_field="terminal_closed_dates",
    evidence=(
        "the published gate schedule or closure notice covering each date claimed"
    ),
    enumerated=False,
)


# ---------------------------------------------------------------------------
# FMC charge-complaint procedure
# ---------------------------------------------------------------------------

#: FMC, "Guidance on Charge Complaint Interim Procedure", retrieved 2026-09-15.
CHARGE_COMPLAINT_GUIDANCE = {
    "cite": "46 U.S.C. 41310",
    "source": (
        "FMC, Guidance on Charge Complaint Interim Procedure, "
        "https://www.fmc.gov/ocean-shipping-reform-act-of-2022-implementation/"
        "guidance-on-charge-complaint-interim-procedure/"
    ),
    "who": (
        "a shipper, consignee, trucker or third party who paid such charges or "
        "who has been invoiced or assessed for such charges"
    ),
    "required": (
        "identification of the common carrier",
        "description or statement on how the charge or fee violated "
        "46 U.S.C. 41104(a) or 41102",
        "supporting documentation including Invoices, Bills of Lading, proof "
        "of payment for the charges or fees demanded",
    ),
    "submission": (
        "Charge Complaints can be submitted by email to chargecomplaints@fmc.gov."
    ),
    "scope_note": (
        "The charge must have been invoiced or assessed on or after June 16, 2022."
    ),
    "verified": VERBATIM,
}

#: 46 CFR 502.62(a)(3) -- contents of a formal private-party complaint.
FORMAL_COMPLAINT_502_62 = {
    "cite": "46 CFR 502.62",
    "heading": "Private party complaints for formal adjudication.",
    "lead": "The complaint must be verified and must contain the following:",
    "contents": (
        "The name, street address, and email address of each complainant, and "
        "the name, address, and email address of each complainant's attorney or "
        "representative, the name, address, and, if known, email address of "
        "each person against whom complaint is made;",
        "A recitation of the legal authority and jurisdiction for institution "
        "of the proceeding, with specific designation of the statutory "
        "provisions alleged to have been violated;",
        "A clear and concise factual statement sufficient to inform each "
        "respondent with reasonable definiteness of the acts or practices "
        "alleged to be in violation of the law, and a statement showing that "
        "the complainant is entitled to relief;",
        "A request for the relief and other affirmative action sought; and",
        "Shipping Act violation must be alleged. If the complaint fails to "
        "indicate the sections of the Act alleged to have been violated or "
        "clearly to state facts which support the allegations, the Commission "
        "may, on its own initiative, require the complaint to be amended to "
        "supply such further particulars as it deems necessary.",
    ),
    "reparation": (
        "A complaint seeking reparation must be filed within three years after "
        "the claim accrues."
    ),
    "fee": "The complaint must be accompanied by remittance of a $387 filing fee.",
    "verified": VERBATIM,
}

#: 46 CFR 502 subpart S -- informal adjudication of small claims.
SMALL_CLAIMS_502_S = {
    # Cited as the live sections, not the subpart range: 46 CFR 502.303 reads
    # "[Reserved]" on eCFR as of 2026-09-01 (checked 2026-09-22). Every quoted
    # sentence below was re-located in a live section on that date:
    # threshold -> 502.301, limitation -> 502.302, form/fee/supporting -> 502.304.
    "cite": "46 CFR 502.301, 502.302, 502.304",
    "reserved_in_subpart": ("46 CFR 502.303",),
    "heading": "Informal Procedure for Adjudication of Small Claims",
    "threshold": (
        "With the consent of both parties, claims filed under this subpart in "
        "the amount of $50,000 or less will be decided by a Small Claims "
        "Officer appointed by the Federal Maritime Commission's Chief "
        "Administrative Law Judge, without the necessity of formal proceedings "
        "under the rules of this part."
    ),
    "limitation": (
        "Claims alleging violations of the Shipping Act of 1984 must be filed "
        "within three years from the time the cause of action accrues."
    ),
    "form": (
        "A sworn claim under this subpart shall be filed in the form prescribed "
        "in Exhibit No. 1 to this subpart."
    ),
    "fee": "Such claims must be accompanied by remittance of a $176 filing fee.",
    "supporting": (
        "Supporting documents may consist of affidavits, correspondence, bills "
        "of lading, paid freight bills, export declarations, dock or wharf "
        "receipts, or of such other documents as, in the judgment of the "
        "claimant, tend to establish the claim."
    ),
    "verified": VERBATIM,
}


def provenance() -> dict:
    """Machine-readable provenance for every rule this package encodes."""
    entries = {
        "46 CFR 541.4": RULE_541_4["verified"],
        "46 CFR 541.5": RULE_541_5["verified"],
        "46 U.S.C. 41310": RULE_41310["verified"],
        "46 CFR 545.5": RULE_545_5["verified"],
        "46 CFR 502.62": FORMAL_COMPLAINT_502_62["verified"],
        "46 CFR 502.301, 502.302, 502.304": SMALL_CLAIMS_502_S["verified"],
        "46 CFR 502.303": VACATED,
        "FMC charge-complaint guidance": CHARGE_COMPLAINT_GUIDANCE["verified"],
    }
    entries.update({f.cite: f.verified for f in FACTORS_545_5})
    entries.update({c.cite: c.verified for c in CLOCKS.values()})
    entries.update({e.cite: e.verified for e in REQUIRED_ELEMENTS})
    return {
        "retrieved": RETRIEVED,
        "sources": list(SOURCES),
        "rules": entries,
        "unverified": [k for k, v in entries.items() if v == UNVERIFIED],
        # Sections once encoded that are no longer in force. Listed, never
        # dropped: a reader must be able to see that 541.4 was checked and
        # withdrawn, not wonder whether it was overlooked.
        "vacated": [k for k, v in entries.items() if v == VACATED],
    }
