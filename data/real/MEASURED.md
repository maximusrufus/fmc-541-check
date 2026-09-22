# Real-invoice measurement — 2026-09-22

**Corpus size: N=1 real case, not the 15+ invoice PDFs a full build would
want.** See `SOURCES.md` for the exhaustive list of sources tried and why
each failed to yield a full real or specimen invoice PDF. This file reports
what the one real data point actually shows, and states plainly what remains
unmeasured. No number below is extrapolated past N=1.

## The one real data point

`cc002_reissued_invoice_001.txt` — built **only** from facts stated verbatim
in the public FMC order in Docket CC-002 (`fmc_cc002_order_to_show_cause_20260306.pdf`,
¶¶18-32), covering one of the 159 real invoices Hapag-Lloyd AG reissued to
Oceana Global Logistics, LLC. **This is not the original invoice** — the
exhibit itself is not in the public record (see `SOURCES.md`). It carries
only: invoice date (2025-04-18), date charge last incurred (2024-11-27),
billing party, billed party, charge type. Every other field the invoice
presumably contained is **genuinely unknown to us**, not absent from the
real document.

### 46 CFR 541.7(a) — timing — reproduces the arithmetic stated in a real FMC order

Running `demurragedesk.ingest` + `screen_invoice` on the record:

```
[unpayable] 46 CFR 541.7(a): Invoice was issued 142 calendar days after the
date charge last incurred, 112 day(s) beyond the 30-day limit. The billed
party is not required to pay the charge.
    math: date charge last incurred 2024-11-27 + 30 calendar days =
    2024-12-27; invoice issued 2025-04-18 (day 142)
```

The FMC's own order (¶29): "All 159 invoices identified in Attachment A were
issued more than 30 days after the date on which the last charge was
incurred." The order's stated range for the 159 invoices is **142-316 days
late** (¶28); this record uses the low end (142 days, the least-favorable
case for finding a violation) and the tool independently reproduces the
figure stated in the order exactly. **1 of 1 real 541.7(a) fact patterns
tested: parser recall = 1/1 (100%), true-miss rate = 1/1 (100%)** — i.e. the
one real invoice the FMC itself found late, the parser also finds late, with
the exact day count the order states. This is the single strongest evidence
point in the corpus, and it is N=1.

### 46 CFR 541.6 — element presence — NOT MEASURED on this record, by design

The parser correctly reports all 18 other elements as "not found" (see the
full run in git history / by re-running the command below) — but this is
**not evidence about the real invoice's actual completeness**, because the
public order never discloses whether those fields were present on the
reissued invoices. Marking them here as a "miss" (true or ingest) would
misrepresent what we know. **This is the honest reason the 541.6 element
check has zero real-invoice validation in this corpus**, not because the
parser was untested — it genuinely cannot be tested against a document we
do not have.

Reproduce:
```
python -m demurragedesk.ingest data/real/cc002_reissued_invoice_001.txt
```

## The headline number a real deployment would want

> "Of N real invoices, M fail 541.6 on a TRUE miss."

**Cannot be stated.** N=1 in this corpus, and that one record has zero
541.6 element data (see above) — the true-miss question is only answerable
for 541.7(a) timing, where the answer is 1 of 1 (matching a real FMC
finding), not for 541.6 completeness. The wake-up trigger in `STATE.md`
(">~20% part-541 defect rate on 90 days of a forwarder's paid invoices") is
**still unmeasured** and requires exactly what this session could not
obtain: real invoice documents, not case citations about them.

## Parser recall — measurable only where we have real field-level truth

| Element / check | Real cases with known ground truth | Parser correct | Recall |
|---|---|---|---|
| 541.7(a) invoice-timing | 1 (this record) | 1 | 100% (n=1) |
| 541.6(a)-(e), all 19 import elements | 0 — public record never discloses presence/absence on a real invoice | — | UNMEASURED |

## What remains genuinely UNMEASURED (do not cite as tested)

- Failure rate of real carrier D&D invoices against the 20-element list —
  needs actual invoice documents (CSV export, text, or PDF), which this
  session could not obtain for free (see `SOURCES.md`).
- PDF ingest time and recall on real carrier PDF layouts (label variants,
  table layouts, currency/date formats) — no real carrier PDF was ever
  obtained to test against.
- Human review time per invoice, for the "hours saved" pitch in the channel
  package — no published figure was found and none is asserted here.
- OCR accuracy on a real scanned invoice — see the OCR section added this
  session (`ingest.ocr_pdf`); the integration test result (ran/skipped) is
  reported separately, and even where it ran it used the CSV/text fixtures
  rendered to image, not a genuinely scanned real invoice, because none was
  available.

## What this DOES support

- The tool's 541.7(a) timing arithmetic reproduces a real Commission finding
  exactly, on the one real case available. That is a fact, not an inference
  about the broader corpus.
- Everything else in this document is a gap statement, on purpose: this
  session raises the validated real-case count from 0 to 1 and documents,
  concretely, what it would take to raise it further — an auditor's or
  forwarder's actual invoice export, contributed via a GitHub issue with a
  redacted sample.
