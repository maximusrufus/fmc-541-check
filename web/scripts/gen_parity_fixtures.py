#!/usr/bin/env python
"""Generate the shared parity fixture set and its NATIVE-CPython verdicts.

The browser runs the same ``demurragedesk`` package under Pyodide, so a
divergence here is not a "port drift" bug (there is no port) but a real one:
a stale bundle, a broken unpack, a coercion that behaves differently under
Emscripten, or a lost dependency. The e2e parity spec replays every payload
below through the page's engine and demands byte-identical results, letter
text included.

Writes e2e/fixtures/parity.json. Regenerate with:
    python scripts/gen_parity_fixtures.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE.parent
REPO = WEB.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(WEB / "py"))

import webapi  # noqa: E402

OUT = WEB / "e2e" / "fixtures" / "parity.json"

LAST = dt.date(2026, 3, 10)
CHARGED = "2026-03-07,2026-03-08,2026-03-09,2026-03-10"
TODAY = "2026-04-20"  # fixed, so the letter text is deterministic

ALL_PRESENT = {e["key"]: "present" for e in webapi.element_catalog("import")}


def _issue(offset: int) -> str:
    return (LAST + dt.timedelta(days=offset)).isoformat()


def _base(**over) -> dict:
    payload = dict(
        invoice_id="PARITY-1",
        invoice_issue_date=_issue(30),
        charge_last_incurred=LAST.isoformat(),
        charge_first_incurred="2026-03-07",
        charge_type="demurrage",
        direction="import",
        billing_party="Synthetic Ocean Lines",
        billing_party_type="ocean_common_carrier",
        billed_party="Synthetic Importer LLC",
        billed_party_role="contracting_party",
        container_number="SYNU1234567",
        bill_of_lading="SYNBL00042",
        port_of_discharge="Port of Example, CA",
        total_amount="1300.00",
        daily_rate="325.00",
        charged_dates=CHARGED,
        stated_dispute_window_days=30,
        elements=dict(ALL_PRESENT),
        today=TODAY,
    )
    payload.update(over)
    return payload


CASES: list[dict] = [
    {
        "name": "day30_clean",
        "why": "Issued on day 30 exactly -- 'within thirty (30) calendar days' includes day 30.",
        "payload": _base(invoice_id="PARITY-DAY30"),
    },
    {
        "name": "day31_late",
        "why": "One day past the 541.7(a) window; unpayable on the clock alone.",
        "payload": _base(invoice_id="PARITY-DAY31", invoice_issue_date=_issue(31)),
    },
    {
        "name": "missing_element_only",
        "why": "Timely (day 30) but omits the allowed free time -- unpayable on 541.6/541.5 alone.",
        "payload": _base(
            invoice_id="PARITY-MISSING",
            elements={**ALL_PRESENT, "541.6(b)(3)": "absent"},
        ),
    },
    {
        "name": "all_unsure",
        "why": "Every element marked unsure. Must produce ZERO defects and a full document queue.",
        "payload": _base(
            invoice_id="PARITY-UNSURE",
            elements={k: "unsure" for k in ALL_PRESENT},
        ),
    },
    {
        "name": "unsure_plus_late",
        "why": "Unsure elements must not suppress a clock defect, nor add one of their own.",
        "payload": _base(
            invoice_id="PARITY-UNSURE-LATE",
            invoice_issue_date=_issue(31),
            elements={k: "unsure" for k in ALL_PRESENT},
        ),
    },
    {
        "name": "nvocc_late_on_upstream",
        "why": "Day 26 from the charge but day 31 from the upstream invoice -- 541.7(b) catches it.",
        "payload": _base(
            invoice_id="PARITY-NVOCC",
            billing_party_type="nvocc",
            billing_party="Synthetic NVOCC Inc",
            upstream_invoice_issue_date="2026-03-05",
            invoice_issue_date="2026-04-05",
        ),
    },
    {
        "name": "nvocc_no_upstream_date",
        "why": "NVOCC that does not disclose its upstream invoice date -- disputable, not unpayable.",
        "payload": _base(
            invoice_id="PARITY-NVOCC-BLIND",
            billing_party_type="nvocc",
            billing_party="Synthetic NVOCC Inc",
        ),
    },
    {
        "name": "facts_asserted_545_5",
        "why": "User asserts closure and government-hold dates -- DISPUTABLE, never unpayable.",
        "payload": _base(
            invoice_id="PARITY-FACTS",
            facts={
                "terminal_closed_dates": "2026-03-08,2026-03-09",
                "government_hold_dates": "2026-03-10",
                "notice_of_availability_given": "no",
            },
        ),
    },
    {
        "name": "facts_unanswered",
        "why": "Facts left blank stay NOT ASSERTED -- evidence gaps, never grounds.",
        "payload": _base(
            invoice_id="PARITY-NOFACTS",
            facts={"terminal_closed_dates": "", "government_hold_dates": "unsure"},
        ),
    },
    {
        "name": "no_amount_supplied",
        "why": "No amount typed -- the tool must refuse to state one.",
        "payload": _base(
            invoice_id="PARITY-NOAMT",
            invoice_issue_date=_issue(31),
            total_amount="",
            daily_rate="",
        ),
    },
    {
        "name": "short_dispute_window",
        "why": "Invoice allows only 10 days to dispute -- 541.8(a) floor is 30.",
        "payload": _base(invoice_id="PARITY-SHORTWIN", stated_dispute_window_days=10),
    },
    {
        "name": "export_direction",
        "why": "Export drops the import-only elements and adds the earliest return date.",
        "payload": _base(
            invoice_id="PARITY-EXPORT",
            direction="export",
            elements={e["key"]: "present" for e in webapi.element_catalog("export")},
        ),
    },
]

CSV_CASE = {
    "name": "csv_batch",
    "why": "Three invoices via the package's own CSV ingest; one late, one clean, one sparse.",
    "today": TODAY,
    # NOTE: ingest._dates splits a charged-date list on ";" or "|", never ",".
    "text": (
        "invoice_number,invoice_date,charge_last_incurred,bill_of_lading,container,"
        "port_of_discharge,liability_basis,invoice_due_date,free_time,free_time_from,"
        "free_time_to,available_date,billed_dates,total_due,tariff,rate_detail,contact,"
        "disputes_url,dispute_timeframes,cert_rules,cert_performance,rate,direction\n"
        "CSV-LATE,2026-04-10,2026-03-10,SYNBL1,SYNU1234567,Port of Example,consignee,"
        "2026-05-10,4,2026-03-03,2026-03-06,2026-03-06,"
        '"2026-03-07;2026-03-08;2026-03-09;2026-03-10",1300.00,TARIFF-1 R5,325/day,'
        "disputes@example.test,https://example.test/d,30 days,yes,yes,325.00,import\n"
        "CSV-CLEAN,2026-04-09,2026-03-10,SYNBL2,SYNU1234568,Port of Example,consignee,"
        "2026-05-09,4,2026-03-03,2026-03-06,2026-03-06,"
        '"2026-03-07;2026-03-08;2026-03-09;2026-03-10",1300.00,TARIFF-1 R5,325/day,'
        "disputes@example.test,https://example.test/d,30 days,yes,yes,325.00,import\n"
        "CSV-SPARSE,2026-04-09,2026-03-10,,,,,,,,,,,,,,,,,,,,import\n"
    ),
}


def main() -> int:
    cases = []
    for case in CASES:
        cases.append({**case, "expected": webapi.screen_payload(dict(case["payload"]))})
    csv_case = {
        **CSV_CASE,
        "expected": webapi.screen_csv(CSV_CASE["text"], CSV_CASE["today"]),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generated_by": "scripts/gen_parity_fixtures.py",
                "note": (
                    "Verdicts below were produced by native CPython importing the "
                    "demurragedesk package directly. The browser must reproduce them "
                    "exactly, letter text included."
                ),
                "today": TODAY,
                "cases": cases,
                "csv_case": csv_case,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    verdicts = {c["name"]: c["expected"]["verdict"] for c in cases}
    print(f"wrote {OUT.relative_to(WEB)} with {len(cases)} single cases + 1 CSV case")
    for name, v in verdicts.items():
        print(f"  {name:28s} {v}")
    print(f"  {'csv_batch':28s} {csv_case['expected']['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
