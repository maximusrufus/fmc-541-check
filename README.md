# fmc-541-check

Screen ocean **demurrage and detention invoices** against the Federal
Maritime Commission's billing rules, 46 CFR part 541 — and 46 CFR 545.5's
"incentive principle" for arguing a charge is unreasonable in addition to
any part-541 defect.

Two ways to run it:

1. **In the browser, nothing uploaded** — `web/site/index.html`, a static
   page that runs this same Python package under Pyodide, client-side.
   A hosted copy runs at https://check.trilatic.com, and the same engine is one of seven desks
   under a single matter at https://desks.trilatic.com. Either way, nothing leaves the browser.
   The original line: — same code, same policy: the page
   is served with `default-src 'self'`, so an invoice you paste never leaves your browser.
2. **From the command line** — `python -m demurragedesk.ingest`, against a
   CSV export or a single PDF/text invoice.

This is not legal advice, and the tool never files, sends, or submits
anything on anyone's behalf. It reports what the regulation itself says
about an invoice's face — the output is a document a person reviews and
sends themselves, or doesn't.

## What it checks

- **46 CFR 541.6** — the 20 elements a demurrage/detention invoice must
  carry (19 apply to an import invoice, 18 to an export invoice; 3 are
  direction-specific). Per 46 CFR 541.5, omitting any required element
  "eliminates any obligation of the billed party to pay the applicable
  charge."
- **46 CFR 541.7(a)** — the invoice must be issued within 30 calendar days
  of the date the charge was last incurred. Late issuance makes the charge
  unpayable on its face, per the same 541.5 consequence.
- **46 CFR 541.7(b)** — the NVOCC re-bill variant: an NVOCC's 30-day clock
  runs from the date *it* received the underlying invoice, not from the
  date the charge was last incurred.
- **46 CFR 541.8** — the mitigation-request timeline (≥30 days for the
  billed party to ask, 30 days for the billing party to try to resolve).
- **46 CFR 545.5** — the incentive-principle "unreasonable practice"
  argument. Only four factors are actually enumerated in the rule — cargo
  availability, empty container return, notice of cargo availability, and
  government inspections (`(c)(2)(i)`-`(iv)`). Terminal closure and
  appointment unavailability are **not** listed in the rule text; they
  reach the analysis through the general incentive principle at `(c)(1)`
  plus the non-preclusion clause at `(f)`. This is a **disputable**
  argument, not a face-of-the-document defect — it needs facts the billed
  party must supply, and the tool models each factor as a tri-state
  (yes / no / unknown), never inferring "no" from silence.

`UNPAYABLE` (541.5/541.6/541.7 defects, visible on the invoice's face,
needing no external fact) and `DISPUTABLE` (545.5 arguments, needing
evidence) are kept distinct throughout — the generated mitigation letter
renders them as separate parts, in that order, and never blurs one into
the other.

### The vacated section

**46 CFR 541.4 is "[Reserved]"** on eCFR as of 2026-09-01 — vacated, no
longer in force. `demurragedesk.rules.provenance()` carries it under a
`vacated` key so the withdrawal stays visible rather than silently
disappearing from the codebase; the tool raises nothing under it.
**46 CFR 502.303** is likewise reserved. Both status checks were verified
against the eCFR versioner API's point-in-time snapshots — see the source
URLs embedded in `demurragedesk/rules.py` and printed by
`python -c "from demurragedesk import provenance; print(provenance())"`.

Every quoted rule string in `rules.py` was retrieved verbatim from two
independent primary sources (GPO/govinfo CFR XML and the eCFR versioner
API), which agreed word for word; see the citation comments at the top of
`rules.py` for the exact URLs and retrieval date.

## Run it

```bash
pip install -e .
python -m demurragedesk.ingest invoices.csv                    # screen a CSV export
python -m demurragedesk.ingest invoices.csv --map mymap.json   # your column names
python -m demurragedesk.ingest invoice.pdf                     # single PDF invoice
python -m demurragedesk.ingest invoices.csv --json             # machine-readable
```

```python
from demurragedesk.ingest import read_csv
from demurragedesk.screen import screen_invoice
from demurragedesk.packet import PacketParty, write_packet

for rec in read_csv("invoices.csv"):
    result = screen_invoice(rec)
    print(result)
```

### In the browser

```bash
cd web
npm install
npm run build       # regenerate site/py/demurragedesk.zip from demurragedesk/*.py
npm run serve       # node scripts/serve.mjs 5189 -- serves site/ with its CSP headers
```

Open `http://localhost:5189`. The page loads Pyodide (~13 MB, first load
only) and runs the actual `demurragedesk` package client-side — there is no
separate JavaScript reimplementation of the rules to drift out of sync.
`npm run build:check` fails if the committed bundle no longer matches the
Python source; run it before any PR that touches `demurragedesk/*.py`.

### Optional: local OCR for scanned PDFs

```bash
pip install -e ".[ocr]"
```

`rapidocr-onnxruntime` (pure pip, CPU-only) plus `pymupdf` for
rasterization. Never a paid API, never a network call.

## What it does NOT do

- **Presence, not truth.** The 541.6 element check confirms a field is
  present on the invoice and reasonably formatted (a date parses, a money
  amount parses); it cannot and does not verify the field's value is
  *correct* — that a stated container number is the real one, that a
  charged amount matches the tariff, or that a date is accurate.
- **Not legal advice.** Every generated document says so, names the party
  it was prepared for, and says it was prepared by the billed party or its
  authorised representative.
- **Never files, sends, or submits anything.** The output is a mitigation
  letter or charge-complaint information packet a person reviews and sends
  themselves — the tool holds no account with the FMC or any carrier and
  makes no outbound call on the user's behalf.
- **No data leaves the browser in the web version.** The CLI reads local
  files only.

## The one real data point

`data/real/` documents an exhaustive, honest attempt to source real (not
synthetic) carrier D&D invoices for validation — see `SOURCES.md` for every
source tried and why each failed to yield one, and `MEASURED.md` for what
the one real, still-pending case actually shows. Summary:

- **FMC Docket CC-002** (Hapag-Lloyd AG, Order to Show Cause, served
  2026-03-06, a real public FMC order — `fmc_cc002_order_to_show_cause_20260306.pdf`)
  found that 159 real invoices were reissued 142-316 days after the date
  each charge was last incurred, a 46 CFR 541.7(a) violation on the
  Commission's own finding.
- `cc002_reissued_invoice_001.txt` is a test record built **only** from
  facts the public order states verbatim (it is explicitly not the real
  invoice, which is not in the public record). Running the 541.7(a) timing
  check against it reproduces the figure the order itself states: 142
  days late, matching the order's cited low end.
- **The 541.6 element-presence check has zero real-invoice validation.**
  The public order never discloses whether the reissued invoices carried
  each of the 20 required elements, so no "miss" is asserted for that
  check against a real document — see `MEASURED.md` for why this is
  reported as a genuine, tested gap rather than papered over.

If you hold real carrier invoices (redact account/container numbers and
amounts as you see fit) and can contribute a test fixture or report a
parsing miss, open an issue — see `CONTRIBUTING.md`.

## Use the rules from another language

`rules/fmc-541.json` is a single generated JSON document carrying every
rule this package encodes (the 20 541.6 elements, the 541.7/541.8 clocks,
541.5's consequence text, the 545.5 factors, and the vacated-sections
list) — generated from, and drift-tested against, the same Python objects
`demurragedesk/screen.py` runs against invoices. `rules/fmc-541.d.ts` has
the TypeScript types, `rules/example.ts` shows computing an invoice
deadline and checking for missing elements, and `rules/README.md` has the
full details, regeneration command, and provenance guarantee.

## Layout

```
demurragedesk/    the rules engine (rules.py, screen.py, ingest.py, packet.py)
tests/            pytest suite, including the CC-002 real-case regression test
data/real/        the one public FMC document + its derived test record
web/              the in-browser self-check page (Pyodide) and its build script
```
