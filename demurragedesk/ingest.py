"""Ingest invoices from CSV exports and from text/PDF invoices.

Two doctrines, both load-bearing:

1. **Presence is evidence, absence is a finding.**  A 46 CFR 541.6 element is
   marked present only when a value was actually found.  We never default,
   never infer, never fill in from another field.  541.5 makes omission the
   whole point of the product, so a helpful guess would destroy the claim.

2. **The reader reports what it could not find.**  ``ExtractionResult`` always
   carries a ``not_found`` list.  For PDFs this is the operator's work queue,
   not a silent gap.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence

from .rules import ELEMENTS_BY_FIELD, REQUIRED_ELEMENTS
from .screen import InvoiceRecord, as_date, as_money

__all__ = [
    "DEFAULT_COLUMN_MAP",
    "ExtractionResult",
    "load_column_map",
    "read_csv",
    "read_text_invoice",
    "read_pdf_invoice",
    "OCREngine",
    "OCRNotConfigured",
    "ocr_pdf",
    "main",
]


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

#: Maps a *record field name* -> the list of CSV header spellings we accept.
#: Real carrier/forwarder exports differ wildly; override with ``--map``.
#:
#: A ``--map`` file is JSON of the same shape, e.g.::
#:
#:     {"container_number": ["CNTR", "Equipment #"],
#:      "invoice_issue_date": ["Inv Dt"]}
#:
#: Entries are MERGED into the default map (your spellings take priority).
DEFAULT_COLUMN_MAP: dict[str, list[str]] = {
    "invoice_id": ["invoice_id", "invoice_number", "invoice no", "inv #"],
    "invoice_issue_date": [
        "invoice_date",
        "invoice_issue_date",
        "issue_date",
        "inv date",
    ],
    "invoice_due_date": ["invoice_due_date", "due_date", "payment due"],
    "charge_last_incurred": [
        "charge_last_incurred",
        "last_incurred",
        "thru_date",
        "charge_to",
    ],
    "charge_first_incurred": ["charge_first_incurred", "from_date", "charge_from"],
    "charge_type": ["charge_type", "charge", "type"],
    "direction": ["direction", "trade", "import_export"],
    "billing_party": ["billing_party", "carrier", "biller"],
    "billing_party_type": ["billing_party_type", "biller_type"],
    "billed_party": ["billed_party", "bill_to", "customer"],
    "billed_party_role": ["billed_party_role", "bill_to_role"],
    "container_number": ["container_number", "container", "cntr", "equipment"],
    "bill_of_lading": ["bill_of_lading", "bl_number", "b/l", "bol"],
    "port_of_discharge": ["port_of_discharge", "pod", "discharge_port"],
    "total_amount": ["total_amount", "amount", "total_due", "amount_due"],
    "daily_rate": ["daily_rate", "rate", "per_diem_rate"],
    "free_time_days": ["free_time_days", "free_time", "free days"],
    "free_time_start": ["free_time_start", "free_time_from"],
    "free_time_end": ["free_time_end", "free_time_to", "last_free_day", "lfd"],
    "container_availability_date": [
        "container_availability_date",
        "available_date",
        "avail",
    ],
    "earliest_return_date": ["earliest_return_date", "erd"],
    "charged_dates": ["charged_dates", "charge_days", "billed_dates"],
    "closure_dates": ["closure_dates", "terminal_closed", "closure"],
    "closure_reason": ["closure_reason"],
    "stated_dispute_window_days": ["dispute_window_days", "dispute_days"],
    "upstream_invoice_issue_date": ["upstream_invoice_date", "received_invoice_date"],
    "basis_for_liability": ["basis_for_liability", "liability_basis"],
    "applicable_rule": ["applicable_rule", "tariff_rule", "tariff"],
    "specific_rate": ["specific_rate", "rate_detail"],
    "dispute_contact": ["dispute_contact", "contact"],
    "dispute_digital_means": ["dispute_url", "dispute_digital_means", "disputes_url"],
    "dispute_timeframes": ["dispute_timeframes"],
    "cert_consistent_with_rules": ["cert_consistent_with_rules", "cert_rules"],
    "cert_performance_did_not_contribute": [
        "cert_performance_did_not_contribute",
        "cert_performance",
    ],
    "also_invoiced_consignee": ["also_invoiced_consignee"],
}

#: Two vocabularies meet in this module and they are NOT identical:
#:
#:   * the ELEMENT vocabulary -- ``RequiredElement.field_name`` in rules.py, which is what
#:     presence detection looks up, and
#:   * the RECORD vocabulary -- ``InvoiceRecord`` attributes, which is how the maps above are keyed.
#:
#: Where an element's field_name has no producer, ``_pick`` finds nothing, the element is marked
#: ABSENT, and 46 CFR 541.5 turns that absence into "the billed party is not required to pay".
#: The failure therefore does NOT degrade gracefully: it manufactures a FALSE UNPAYABLE on an
#: invoice that is in fact complete, which is the one error this product cannot afford to make.
#:
#: These aliases give every element field_name a producer. ``tests/test_ingest_field_coverage.py``
#: fails if any required element ever lacks one again, in any ingest path.
_ELEMENT_FIELD_ALIASES = {
    "invoice_date": "invoice_issue_date",  # 541.6(b)(1)
    "total_amount_due": "total_amount",  # 541.6(c)(1)
    "specific_rate": "daily_rate",  # 541.6(c)(3), text/PDF path only
}

for _element_field, _record_field in _ELEMENT_FIELD_ALIASES.items():
    # setdefault: an explicit entry above always wins over the alias.
    DEFAULT_COLUMN_MAP.setdefault(
        _element_field, list(DEFAULT_COLUMN_MAP[_record_field])
    )

_TRUE = {"1", "true", "yes", "y", "t"}


def load_column_map(path: str | Path | None) -> dict[str, list[str]]:
    """Merge a JSON ``--map`` override into :data:`DEFAULT_COLUMN_MAP`."""
    merged = {k: list(v) for k, v in DEFAULT_COLUMN_MAP.items()}
    if path is None:
        return merged
    user = json.loads(Path(path).read_text(encoding="utf-8"))
    for fieldname, spellings in user.items():
        if isinstance(spellings, str):
            spellings = [spellings]
        merged.setdefault(fieldname, [])
        # user spellings win by being tried first
        merged[fieldname] = list(spellings) + [
            s for s in merged[fieldname] if s not in spellings
        ]
    return merged


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _pick(row: dict[str, str], spellings: Sequence[str]) -> str | None:
    normed = {_norm(k): v for k, v in row.items()}
    for spelling in spellings:
        value = normed.get(_norm(spelling))
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _dates(raw: str | None) -> tuple[date, ...]:
    if not raw:
        return ()
    parts = [p.strip() for p in re.split(r"[;|]", raw) if p.strip()]
    return tuple(as_date(p) for p in parts)


def _record_from_row(row: dict[str, str], cmap: dict[str, list[str]]) -> InvoiceRecord:
    get = lambda f: _pick(row, cmap.get(f, [f]))  # noqa: E731

    present: set[str] = set()
    for el in REQUIRED_ELEMENTS:
        if el.field_name and get(el.field_name) is not None:
            present.add(el.key)

    issue = get("invoice_issue_date")
    last = get("charge_last_incurred")
    if issue is None or last is None:
        raise ValueError(
            "a row needs at least an invoice issue date and the date the charge "
            f"was last incurred to be screened; got issue={issue!r} last={last!r}"
        )

    kwargs: dict[str, Any] = {
        "invoice_id": get("invoice_id") or "(unnumbered)",
        "invoice_issue_date": as_date(issue),
        "charge_last_incurred": as_date(last),
        "charge_type": (get("charge_type") or "demurrage").lower(),
        "direction": (get("direction") or "import").lower(),
        "billing_party": get("billing_party") or "",
        "billing_party_type": (
            get("billing_party_type") or "ocean_common_carrier"
        ).lower(),
        "billed_party": get("billed_party") or "",
        "billed_party_role": (get("billed_party_role") or "contracting_party").lower(),
        "container_number": get("container_number") or "",
        "bill_of_lading": get("bill_of_lading") or "",
        "port_of_discharge": get("port_of_discharge") or "",
        "total_amount": as_money(get("total_amount") or "0"),
        "charged_dates": _dates(get("charged_dates")),
        "closure_dates": _dates(get("closure_dates")),
        "closure_reason": get("closure_reason") or "",
        "present_fields": frozenset(present),
        "source": "csv",
    }
    if (v := get("daily_rate")) is not None:
        kwargs["daily_rate"] = as_money(v)
    if (v := get("free_time_days")) is not None:
        kwargs["free_time_days"] = int(Decimal(v))
    if (v := get("charge_first_incurred")) is not None:
        kwargs["charge_first_incurred"] = as_date(v)
    if (v := get("stated_dispute_window_days")) is not None:
        kwargs["stated_dispute_window_days"] = int(Decimal(v))
    if (v := get("upstream_invoice_issue_date")) is not None:
        kwargs["upstream_invoice_issue_date"] = as_date(v)
    if (v := get("also_invoiced_consignee")) is not None:
        kwargs["also_invoiced_consignee"] = v.lower() in _TRUE
    return InvoiceRecord(**kwargs)


def read_csv(
    path: str | Path, column_map: dict[str, list[str]] | None = None
) -> list[InvoiceRecord]:
    cmap = column_map or DEFAULT_COLUMN_MAP
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [_record_from_row(row, cmap) for row in csv.DictReader(fh)]


# ---------------------------------------------------------------------------
# Text / PDF invoices
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """What a free-text/PDF reader could and could not find.

    ``record`` is ``None`` when the two fields the clock arithmetic needs
    (invoice issue date, date the charge was last incurred) were not both
    found.  We do not guess either one.
    """

    fields: dict[str, Any] = field(default_factory=dict)
    found: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    record: InvoiceRecord | None = None
    text: str = ""

    def report(self) -> str:
        lines = [f"Found {len(self.found)} field(s): " + ", ".join(sorted(self.found))]
        if self.not_found:
            lines.append(
                "COULD NOT FIND ("
                + str(len(self.not_found))
                + "), not guessed: "
                + ", ".join(sorted(self.not_found))
            )
        if self.record is None:
            lines.append(
                "No record built: the invoice issue date and/or the date the "
                "charge was last incurred were not found. Supply them manually."
            )
        return "\n".join(lines)


# ISO 6346 container number: 4 letters (4th usually U/J/Z) + 7 digits.
_RE_CONTAINER = re.compile(r"\b([A-Z]{3}[UJZ]\s?\d{6}\s?\d)\b")
_RE_MONEY = re.compile(r"\$\s?([0-9][0-9,]*\.?\d{0,2})")
_RE_DATE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)

_LABELS: dict[str, list[str]] = {
    "invoice_id": ["invoice number", "invoice no", "invoice #", "invoice id"],
    "invoice_issue_date": ["invoice date", "date of invoice", "issued"],
    "invoice_due_date": ["due date", "payment due"],
    "charge_last_incurred": ["last incurred", "charges through", "through", "thru"],
    "bill_of_lading": ["bill of lading", "b/l no", "bl number", "b/l"],
    "container_number": ["container number", "container no", "container"],
    "port_of_discharge": ["port of discharge", "discharge port"],
    "free_time_days": ["free time", "free days"],
    "free_time_start": ["free time start", "free time from"],
    "free_time_end": ["free time end", "last free day"],
    "container_availability_date": ["container availability", "available for pickup"],
    "earliest_return_date": ["earliest return date"],
    "total_amount": ["total amount due", "total due", "amount due", "total"],
    "daily_rate": ["daily rate", "per diem rate", "rate per day"],
    "applicable_rule": ["tariff", "rule number", "service contract"],
    "basis_for_liability": ["party of interest", "basis for liability", "liable"],
    "dispute_contact": ["contact", "questions", "email", "telephone"],
    "dispute_digital_means": ["http", "https", "qr code"],
    "dispute_timeframes": ["request within", "must request", "days to request"],
    "cert_consistent_with_rules": ["consistent with", "545.5"],
    "cert_performance_did_not_contribute": ["did not cause or contribute"],
    "charged_dates": ["dates charged", "days charged", "charged for"],
}

for _element_field, _record_field in _ELEMENT_FIELD_ALIASES.items():
    # Same invariant as the column map: no element field_name may be unfindable here either.
    _LABELS.setdefault(_element_field, list(_LABELS[_record_field]))


def _value_after_label(text: str, labels: Sequence[str]) -> str | None:
    for label in labels:
        m = re.search(re.escape(label) + r"\s*[:#-]?\s*(.+)", text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if value:
                return value[:200]
    return None


def read_text_invoice(text: str, *, invoice_id: str | None = None) -> ExtractionResult:
    """Extract what we can from a plain-text invoice. Never guesses."""
    res = ExtractionResult(text=text)

    for fname, labels in _LABELS.items():
        raw = _value_after_label(text, labels)
        if raw is None:
            res.not_found.append(fname)
            continue
        res.fields[fname] = raw
        res.found.append(fname)

    # Tighten a few fields with dedicated patterns where a label match is loose.
    if m := _RE_CONTAINER.search(text):
        res.fields["container_number"] = m.group(1).replace(" ", "")
        if "container_number" in res.not_found:
            res.not_found.remove("container_number")
            res.found.append("container_number")

    def _as_date_or_drop(fname: str) -> date | None:
        raw = res.fields.get(fname)
        if raw is None:
            return None
        m = _RE_DATE.search(str(raw))
        if not m:
            return None
        return _parse_loose_date(m.group(1))

    def _as_money_or_drop(fname: str) -> Decimal | None:
        raw = res.fields.get(fname)
        if raw is None:
            return None
        m = _RE_MONEY.search(str(raw))
        if not m:
            return None
        try:
            return as_money(m.group(1))
        except (InvalidOperation, TypeError):
            return None

    issue = _as_date_or_drop("invoice_issue_date")
    last = _as_date_or_drop("charge_last_incurred")
    total = _as_money_or_drop("total_amount")
    rate = _as_money_or_drop("daily_rate")

    for fname, parsed in (
        ("invoice_issue_date", issue),
        ("charge_last_incurred", last),
        ("total_amount", total),
        ("daily_rate", rate),
    ):
        if fname in res.fields and parsed is None:
            # a label matched but the value was not parseable -- that is a
            # NOT-FOUND, not a guess.
            res.fields.pop(fname)
            if fname in res.found:
                res.found.remove(fname)
            res.not_found.append(fname)
        elif parsed is not None:
            res.fields[fname] = parsed

    present = {ELEMENTS_BY_FIELD[f].key for f in res.fields if f in ELEMENTS_BY_FIELD}

    if issue is not None and last is not None:
        res.record = InvoiceRecord(
            invoice_id=invoice_id
            or str(res.fields.get("invoice_id", "(unnumbered)"))[:64],
            invoice_issue_date=issue,
            charge_last_incurred=last,
            container_number=str(res.fields.get("container_number", "")),
            bill_of_lading=str(res.fields.get("bill_of_lading", ""))[:64],
            port_of_discharge=str(res.fields.get("port_of_discharge", ""))[:64],
            total_amount=total if total is not None else Decimal("0"),
            daily_rate=rate,
            present_fields=frozenset(present),
            unresolved_fields=tuple(sorted(res.not_found)),
            source="text",
        )
    return res


def _parse_loose_date(raw: str) -> date | None:
    raw = raw.strip().rstrip(",")
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%b %d %Y",
        "%B %d %Y",
        "%b. %d %Y",
    ):
        try:
            return datetime.strptime(raw.replace(",", ""), fmt).date()
        except ValueError:
            continue
    return None


def read_pdf_invoice(
    path: str | Path, *, invoice_id: str | None = None
) -> ExtractionResult:
    """Extract text from a PDF with pypdf, then run the text reader.

    A scanned (image-only) PDF yields no text; we say so rather than returning
    an empty-but-confident result. Use :func:`ocr_pdf` to read it via OCR.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pypdf is required to read PDF invoices") from exc

    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        res = ExtractionResult(text="")
        res.not_found = sorted(_LABELS)
        res.fields["_note"] = (
            "No extractable text. This is likely a scanned image PDF; it needs "
            "OCR or manual entry. Nothing was inferred."
        )
        return res
    return read_text_invoice(text, invoice_id=invoice_id)


# ---------------------------------------------------------------------------
# Scanned (image-only) PDF ingest via local OCR
# ---------------------------------------------------------------------------


class OCRNotConfigured(RuntimeError):
    """No free/local OCR engine and no PDF rasterizer are both installed.

    We never call a paid OCR service. This tool checks, in order: an
    injected ``engine`` (tests use a fake); ``rapidocr_onnxruntime``
    (pure-pip, CPU-only, no system install -- preferred); a ``tesseract``
    binary on PATH via ``pytesseract``. Rasterizing the PDF's pages to
    images needs ``pymupdf`` (``fitz``) or ``pdf2image`` (which itself needs
    a system ``poppler`` install) -- whichever is available.
    """


class OCREngine:
    """Minimal interface an OCR engine must satisfy: ``read(image) -> str``.

    ``image`` is whatever the rasterizer produced (a PIL Image or a numpy
    array) -- fakes in tests can accept anything and just return text.
    """

    def read(self, image: Any) -> str:  # pragma: no cover - interface only
        raise NotImplementedError


class _RapidOCREngine(OCREngine):
    """Wraps ``rapidocr_onnxruntime.RapidOCR`` -- free, pip-only, CPU."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR  # lazy import

        self._ocr = RapidOCR()

    def read(self, image: Any) -> str:
        result, _elapse = self._ocr(image)
        if not result:
            return ""
        # result: list of [box, text, score] -- box's top-left y sorts reading order.
        rows = sorted(result, key=lambda r: (r[0][0][1], r[0][0][0]))
        return "\n".join(r[1] for r in rows)


class _TesseractEngine(OCREngine):
    """Wraps ``pytesseract`` against a ``tesseract`` binary on PATH."""

    def __init__(self) -> None:
        import pytesseract  # lazy import

        self._pytesseract = pytesseract

    def read(self, image: Any) -> str:
        return self._pytesseract.image_to_string(image)


def _detect_ocr_engine() -> OCREngine:
    """Free-first escalation: rapidocr (pip-only) before tesseract (system binary)."""
    try:
        return _RapidOCREngine()
    except ImportError:
        pass
    import shutil

    try:
        import pytesseract  # noqa: F401
    except ImportError:
        pass
    else:
        if shutil.which("tesseract") is not None:
            return _TesseractEngine()
    raise OCRNotConfigured(
        "No local OCR engine found. Install rapidocr-onnxruntime "
        "(`pip install rapidocr-onnxruntime`, pure pip, CPU, no paid "
        "service) or a tesseract binary on PATH plus `pip install "
        "pytesseract`. We never call a paid OCR API."
    )


def _rasterize_pdf(path: str | Path):
    """Yield one page image per page, using whichever rasterizer is installed."""
    try:
        import fitz  # pymupdf  # lazy import
    except ImportError:
        pass
    else:
        doc = fitz.open(str(path))
        try:
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                yield pix.tobytes("png")
        finally:
            doc.close()
        return

    try:
        from pdf2image import convert_from_path  # lazy import
    except ImportError as exc:
        raise OCRNotConfigured(
            "No PDF rasterizer found. Install pymupdf "
            "(`pip install pymupdf`, pure pip) or pdf2image (needs a "
            "system poppler install) to rasterize a scanned PDF for OCR."
        ) from exc
    for img in convert_from_path(str(path), dpi=300):
        yield img


def ocr_pdf(
    path: str | Path,
    *,
    invoice_id: str | None = None,
    engine: OCREngine | None = None,
) -> ExtractionResult:
    """Read a scanned (image-only) PDF invoice via local OCR.

    Never calls a paid API. Raises :class:`OCRNotConfigured` with a clear
    message if no free/local engine (and, separately, no PDF rasterizer) is
    installed -- it does not silently fall back to guessing. Every field
    extracted this way is marked ``source="ocr"`` on the resulting
    :class:`~demurragedesk.screen.InvoiceRecord`; :mod:`demurragedesk.packet`
    surfaces that in the cover summary so a reader knows the fields came from
    an OCR read, not a verified transcription.
    """
    ocr = engine or _detect_ocr_engine()
    pages_text: list[str] = []
    for image in _rasterize_pdf(path):
        pages_text.append(ocr.read(image))
    text = "\n".join(pages_text)

    res = read_text_invoice(text, invoice_id=invoice_id)
    res.text = text
    if res.record is not None:
        res.record.source = "ocr"
    return res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="demurragedesk.ingest",
        description="Ingest demurrage/detention invoices and screen them "
        "against 46 CFR part 541.",
    )
    ap.add_argument("path", help="CSV export, .txt invoice, or .pdf invoice")
    ap.add_argument(
        "--map",
        dest="map_path",
        default=None,
        help="JSON column-map override for CSV ingest",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument(
        "--ocr",
        action="store_true",
        help="if a PDF has no extractable text, retry it with local OCR "
        "instead of stopping",
    )
    args = ap.parse_args(argv)

    from .screen import screen_invoice

    p = Path(args.path)
    if p.suffix.lower() == ".csv":
        records = read_csv(p, load_column_map(args.map_path))
    elif p.suffix.lower() == ".pdf":
        res = read_pdf_invoice(p)
        if res.record is None and args.ocr:
            print("No extractable text; retrying with local OCR...")
            res = ocr_pdf(p)
        print(res.report())
        records = [res.record] if res.record else []
    else:
        res = read_text_invoice(p.read_text(encoding="utf-8"))
        print(res.report())
        records = [res.record] if res.record else []

    results = [screen_invoice(r) for r in records]
    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        for r in results:
            print(
                f"\n=== {r.record.invoice_id} "
                f"({'UNPAYABLE' if r.unpayable else 'defects' if not r.clean else 'clean'}) ==="
            )
            for d in r.defects:
                print(f"  [{d.consequence.value}] {d.cite}: {d.summary}")
                if d.math:
                    print(f"      math: {d.math}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
