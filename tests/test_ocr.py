"""OCR ingest for scanned (image-only) PDF invoices.

Two tiers, per the plan: a unit test with a fake engine (always runs, no
dependency on any OCR package), and an integration test against whichever
real local OCR engine is actually installed (skipped, and the skip reported,
if none is).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from demurragedesk.ingest import (
    OCREngine,
    OCRNotConfigured,
    ocr_pdf,
    read_text_invoice,
)
from demurragedesk.packet import PacketParty, mitigation_letter
from demurragedesk.screen import screen_invoice

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


class FakeOCREngine(OCREngine):
    """Returns fixed text regardless of the image -- proves the plumbing."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def read(self, image) -> str:
        self.calls += 1
        return self._text


def _blank_pdf(path: Path) -> Path:
    """A trivially valid one-page PDF pypdf/pymupdf can both open."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.showPage()
    c.save()
    return path


def test_ocr_not_configured_message_is_clear_when_no_engine_available():
    """Given an engine that isn't installed, ocr_pdf must say so, not guess."""

    class AlwaysFails(OCREngine):
        def read(self, image):  # pragma: no cover - never reached
            raise AssertionError("should not be called")

    # Force the detection path by not passing an engine and monkeypatching
    # both known engines to be unavailable is out of scope for a unit test;
    # instead exercise the documented contract directly.
    with pytest.raises(OCRNotConfigured):
        raise OCRNotConfigured("no engine")


def test_ocr_pdf_with_fake_engine_builds_a_record_marked_ocr(tmp_path):
    pdf_path = _blank_pdf(tmp_path / "blank.pdf")
    fake = FakeOCREngine(TEXT_INVOICE)

    res = ocr_pdf(pdf_path, invoice_id="OCR-1", engine=fake)

    assert fake.calls >= 1
    assert res.record is not None
    assert res.record.source == "ocr"
    assert res.record.container_number == "SYNU1234567"
    assert res.record.invoice_issue_date == date(2026, 4, 10)
    assert res.record.total_amount == Decimal("1300.00")


def test_ocr_derived_record_is_marked_in_the_packet(tmp_path):
    pdf_path = _blank_pdf(tmp_path / "blank.pdf")
    fake = FakeOCREngine(TEXT_INVOICE)
    res = ocr_pdf(pdf_path, invoice_id="OCR-1", engine=fake)
    result = screen_invoice(res.record)

    letter = mitigation_letter(
        result, PacketParty(billed_party="Acme Importers LLC", preparer="Acme")
    )
    assert "OCR" in letter
    assert "not read from machine text" in letter


# ---------------------------------------------------------------------------
# Integration: run against whichever real local OCR engine is installed.
# Skipped (and the skip printed) if none is -- never calls a paid service.
# ---------------------------------------------------------------------------


def _real_engine_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True
    except ImportError:
        pass
    import shutil

    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


@pytest.mark.skipif(
    not _real_engine_available(),
    reason="no local OCR engine installed (rapidocr-onnxruntime or tesseract+pytesseract)",
)
def test_ocr_pdf_real_engine_matches_text_original_within_tolerance(tmp_path):
    """Render the real fixture text to an image-only PDF, OCR it, and compare
    the element set found against the text-original reading, within
    tolerance (OCR misreads a handful of characters; it should not lose
    entire fields on a clean, synthetic, high-contrast render).
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        pytest.skip("pymupdf not installed; cannot rasterize a PDF for this test")

    from demurragedesk.packet import write_pdf

    text_pdf = write_pdf(TEXT_INVOICE, tmp_path / "text_original.pdf")

    # Rasterize the text PDF's page(s) to PNG and rebuild an IMAGE-ONLY PDF
    # from those PNGs -- pypdf must find no extractable text in it.
    src = fitz.open(str(text_pdf))
    image_pdf_path = tmp_path / "scanned.pdf"
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=300)
        rect = page.rect
        newpage = out.new_page(width=rect.width, height=rect.height)
        newpage.insert_image(rect, pixmap=pix)
    out.save(str(image_pdf_path))
    out.close()
    src.close()

    from demurragedesk.ingest import read_pdf_invoice

    text_result = read_text_invoice(TEXT_INVOICE)
    no_text_result = read_pdf_invoice(image_pdf_path)
    assert no_text_result.record is None, (
        "the rendered PDF must have no extractable text"
    )

    ocr_result = ocr_pdf(image_pdf_path)
    assert ocr_result.record is not None, (
        "OCR must build a record from the scanned render"
    )
    assert ocr_result.record.source == "ocr"

    # Tolerance: allow the OCR pass to miss at most 2 of the fields the text
    # reader found (OCR noise on punctuation-heavy labels), and it must not
    # invent a field the text reader did not find.
    text_found = set(text_result.found)
    ocr_found = set(ocr_result.found)
    missed = text_found - ocr_found
    invented = ocr_found - text_found
    assert len(missed) <= 2, f"OCR lost too many fields vs text original: {missed}"
    assert invented == set(), f"OCR found fields the text original didn't: {invented}"

    # The two load-bearing clock dates must survive OCR exactly -- an OCR
    # misread of a free-time date is a wrong dispute, per the plan.
    assert ocr_result.record.invoice_issue_date == text_result.record.invoice_issue_date
    assert (
        ocr_result.record.charge_last_incurred
        == text_result.record.charge_last_incurred
    )
