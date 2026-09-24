# rules/fmc-541.json

A single, generated JSON document carrying every rule `demurragedesk`
encodes: the 20 minimum-content elements of 46 CFR 541.6, the 30-day
issuance/mitigation clocks of 46 CFR 541.7/541.8, the 541.5 consequence
text, the six 46 CFR 545.5 reasonableness factors, and the list of
sections checked and found vacated ("[Reserved]"). It exists so a
project in another language (this file was requested by an engineer
implementing 46 CFR 541 timelines in TypeScript) doesn't have to retype
citations or quoted regulatory text by hand.

## This file is generated. Never hand-edit it.

It is produced by `demurragedesk/export_rules.py`, which imports the
same Python objects `demurragedesk/screen.py` checks invoices against
and serializes their fields — every `text` value in the JSON is the
exact string the engine uses, not a retyped copy.

To regenerate after any change to `demurragedesk/rules.py`:

```bash
python -m demurragedesk.export_rules --out rules/fmc-541.json
```

`tests/test_export_rules.py` fails if the committed file no longer
matches a fresh `export()` call — the same drift-guard pattern
`web/`'s `npm run build:check` uses for the Pyodide bundle.

## Using it from another language

- `rules/fmc-541.d.ts` — TypeScript interfaces for the document (no
  runtime code, no dependencies).
- `rules/example.ts` — a ~30-line example computing an invoice deadline
  (`invoiceDeadline`, 46 CFR 541.7(a)/(b), calendar days) and checking
  which 541.6 elements are missing from a parsed invoice
  (`missingElements`).
- `rules/test_example.test.mjs` — a Node test exercising both example
  functions against a fixture date; run with `node --test "rules/*.test.mjs"`.

The JSON has no schema dependency beyond what `fmc-541.d.ts` declares —
plain `JSON.parse` in any language works.

## The provenance guarantee

Every element/clock/factor's `text` field is regulatory text retrieved
**verbatim** from two independent primary sources (govinfo.gov CFR XML
and the eCFR versioner API), which agreed word for word — see
`demurragedesk/rules.py`'s module docstring for the exact source URLs
and retrieval date, also carried in the JSON's `generated_from` and
`provenance` blocks. A `verified` field of `"VERBATIM"` means the text
was actually retrieved and checked this way; there are currently no
`"UNVERIFIED"` entries anywhere in the document.

**Reserved sections are listed, never enforced.** `vacated` names two
sections that were checked and found withdrawn on eCFR ("[Reserved]"):
`46 CFR 541.4` (who may be invoiced) and `46 CFR 502.303` (part of the
small-claims subpart, whose live content was relocated to 502.301,
502.302, and 502.304 — see `rules.py`'s `SMALL_CLAIMS_502_S` comment).
Nothing in `demurragedesk/screen.py` raises a defect under either
citation; they're kept visible here so a reader can see the section was
checked and withdrawn, not silently dropped.

## CC-002 note

`README.md` at the repo root documents FMC Docket CC-002 (Hapag-Lloyd,
Order to Show Cause) as the one real-world validation point for the
541.7(a) timing check. Whether a **reissued** invoice restarts the
541.7(a) clock from its reissue date, or remains bound by the original
"last incurred" date, is an open question pending a Commission
decision expected around **2026-10-08** — this export does not take a
position on it; `days`/`trigger` for `541.7(a)` describe only the
undisputed baseline rule (30 calendar days from the date the charge was
last incurred).
