"""Synthetic invoice fixtures.

Every fixture here is INVENTED. No real carrier, container, bill of lading, or
client appears anywhere in this repository. Container numbers are
ISO-6346-shaped but deliberately fictional.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .rules import required_keys
from .screen import DisputeFacts, InvoiceRecord

__all__ = [
    "ALL_IMPORT_KEYS",
    "clean_invoice",
    "day31_invoice",
    "missing_elements_invoice",
    "nvocc_rebill_invoice",
    "port_closure_invoice",
    "facts_invoice",
    "CHARGED_DATES",
    "ALL_FIXTURES",
]

ALL_IMPORT_KEYS = frozenset(required_keys("import"))

_LAST_INCURRED = date(2026, 3, 10)
_CHARGED = (date(2026, 3, 7), date(2026, 3, 8), date(2026, 3, 9), date(2026, 3, 10))
_RATE = Decimal("325.00")
_TOTAL = _RATE * len(_CHARGED)  # 1300.00


def _base(**over) -> InvoiceRecord:
    kwargs = dict(
        invoice_id="SYN-0001",
        invoice_issue_date=_LAST_INCURRED + timedelta(days=30),  # exactly 30: compliant
        charge_last_incurred=_LAST_INCURRED,
        charge_first_incurred=_CHARGED[0],
        charge_type="demurrage",
        direction="import",
        billing_party="Synthetic Ocean Lines",
        billing_party_type="ocean_common_carrier",
        billed_party="Synthetic Importer LLC",
        billed_party_role="contracting_party",
        container_number="SYNU1234567",
        bill_of_lading="SYNBL00042",
        port_of_discharge="Port of Example, CA",
        total_amount=_TOTAL,
        daily_rate=_RATE,
        free_time_days=4,
        charged_dates=_CHARGED,
        stated_dispute_window_days=30,
        present_fields=ALL_IMPORT_KEYS,
        source="fixture",
    )
    kwargs.update(over)
    return InvoiceRecord(**kwargs)


def clean_invoice() -> InvoiceRecord:
    """Fully compliant: every element present, issued on day 30 exactly."""
    return _base()


def day31_invoice() -> InvoiceRecord:
    """Identical to the clean invoice but issued one day late -- 541.7(a)."""
    return _base(
        invoice_id="SYN-0002-LATE",
        invoice_issue_date=_LAST_INCURRED + timedelta(days=31),
    )


def missing_elements_invoice() -> InvoiceRecord:
    """Omits four required minimum elements -- 541.6 / 541.5.

    Omitted: allowed free time in days; the applicable tariff/contract rule;
    the digital means for disputing; and the performance certification.
    """
    omitted = {"541.6(b)(3)", "541.6(c)(2)", "541.6(d)(2)", "541.6(e)(2)"}
    return _base(
        invoice_id="SYN-0003-MISSING",
        present_fields=ALL_IMPORT_KEYS - omitted,
        free_time_days=None,
    )


def nvocc_rebill_invoice(*, late: bool = True) -> InvoiceRecord:
    """An NVOCC re-bill; its clock runs from the invoice IT received -- 541.7(b).

    With ``late=True`` the re-bill is day 31 from the upstream invoice, yet only
    day 26 from the date the charge was last incurred -- so a screen that used
    541.7(a) instead of 541.7(b) would wrongly pass it.
    """
    upstream = _LAST_INCURRED - timedelta(days=5)
    offset = 31 if late else 30
    return _base(
        invoice_id="SYN-0004-NVOCC" + ("-LATE" if late else ""),
        billing_party="Synthetic NVOCC Inc",
        billing_party_type="nvocc",
        upstream_invoice_issue_date=upstream,
        invoice_issue_date=upstream + timedelta(days=offset),
    )


def port_closure_invoice() -> InvoiceRecord:
    """Charges accrue across days the terminal was closed."""
    closed = (date(2026, 3, 8), date(2026, 3, 9))
    return _base(
        invoice_id="SYN-0005-CLOSURE",
        closure_dates=closed,
        closure_reason="terminal closed, published gate closure",
    )


def facts_invoice(**facts) -> InvoiceRecord:
    """A compliant invoice plus client-supplied 46 CFR 545.5 facts.

    Anything not passed stays ``None`` -- NOT ASSERTED -- which is the whole
    point: an unsupplied fact must never become an allegation.
    """
    return _base(invoice_id="SYN-0006-FACTS", facts=DisputeFacts(**facts))


#: The dates the fixture invoices actually charge for.
CHARGED_DATES = _CHARGED


ALL_FIXTURES = {
    "clean": clean_invoice,
    "day31": day31_invoice,
    "missing_elements": missing_elements_invoice,
    "nvocc_rebill": nvocc_rebill_invoice,
    "port_closure": port_closure_invoice,
    "facts": facts_invoice,
}
