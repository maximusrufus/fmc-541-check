"""DemurrageDesk -- screen ocean demurrage & detention invoices against
46 CFR part 541 (FMC Demurrage and Detention Billing Requirements).

Not legal advice. Prepared for the billed party or its authorised
representative.
"""

from .rules import Consequence, provenance
from .screen import (
    Defect,
    InvoiceRecord,
    ScreenResult,
    as_date,
    as_money,
    screen_all,
    screen_invoice,
)

__version__ = "0.1.0"
__all__ = [
    "Consequence",
    "Defect",
    "InvoiceRecord",
    "ScreenResult",
    "as_date",
    "as_money",
    "provenance",
    "screen_all",
    "screen_invoice",
]
