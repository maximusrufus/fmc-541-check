# Real-invoice corpus — sources and attempts, 2026-09-22

**Result up front: no full real or carrier-specimen D&D invoice PDF was found
free and public in this session.** This file records every source tried, its
HTTP status, and why it did not yield a screenable invoice document, so the
gap is falsifiable rather than asserted. Fetches used
`-A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"`.

## What we do have: one real, verified enforcement case

**FMC Docket CC-002**, *Hapag-Lloyd AG — Investigation for Compliance with
46 U.S.C. § 41104(a) under the Charge Complaint Procedures of 46 U.S.C.
§ 41310*, Order Directing Hapag-Lloyd AG to Show Cause, served 2026-03-06.

- Source: `https://www2.fmc.gov/readingroom/documents/135094` (redirects,
  final 200; PDF, 11 pages) — saved as
  `fmc_cc002_order_to_show_cause_20260306.pdf` in this directory.
- Listing page: `https://www2.fmc.gov/readingroom/proceeding/CC-002/` (200).
- This is a **real, adjudicated FMC order**, not a specimen. It quotes exact
  facts about 159 real invoices (Attachment A) that the Commission found:
  originally issued 2-13 days after the last charge (compliant with
  46 CFR 541.7(a)), then **reissued** on 2025-04-18 for the same charges,
  142-316 days after the date the charge was last incurred — a violation of
  541.7(a) on the Commission's own finding (¶¶18-32 of the order).
- **The invoice images/exhibits themselves (Attachment A, and the "Initial
  Invoices"/"Reissued Invoices" exhibits to the Rutgers Declaration) are
  NOT in the public record.** Hapag-Lloyd's response includes a "Motion for
  Confidential Treatment" over portions of its filing (doc 136178, fetched
  200, then discarded — procedural only), and the Bureau's response
  concedes portions are confidential. We could not locate the underlying
  invoice PDFs anywhere in the public reading room.
- We therefore built **one real-case-derived test record**
  (`cc002_reissued_invoice_001.txt`, this directory) using **only the facts
  the public order states verbatim** — invoice numbering convention,
  the carrier, the billed party, the real date range, and the real 541.7(a)
  violation the Commission itself found. It is explicitly NOT a
  reproduction of the original invoice (we do not have it) and is labeled
  as such in the file and in `MEASURED.md`. Only the 46 CFR 541.7(a) timing
  check is validated against it — the 541.6 element-presence check is
  **not run** on this record because the public order does not disclose
  whether the reissued invoices in fact carried each of the 20 elements.

## Carrier "how to read your invoice" / specimen pages — all blocked or absent

| Carrier | URL tried | Result |
|---|---|---|
| Hapag-Lloyd | `hapag-lloyd.com/en/online-business/demurrage-detention.html` | HTTP 403 (bot-blocked) |
| Hapag-Lloyd | `hapag-lloyd.com/content/dam/website/downloads/dnd/dnd-invoice-guide.pdf` (guessed path) | HTTP 404 |
| Maersk | `maersk.com/support/dispute-management` | HTTP 404 |
| CMA CGM | `cma-cgm.com/ebusiness/demurrage-detention` | HTTP 403 |
| CMA CGM | `cma-cgm.com/static/CMA/media/demurrage-detention-invoice-guide.pdf` (guessed) | HTTP 403 |
| MSC | `msc.com/en/local-information/demurrage-and-detention` | HTTP 403 |
| MSC | `msc.com/globalassets/demurrage-and-detention-guide.pdf` (guessed) | HTTP 403 |
| COSCO SHIPPING | `coscoshipping.com` | HTTP 200 (homepage only; no D&D invoice specimen located within budget) |
| Evergreen | `evergreen-line.com` | HTTP 200 (homepage only; not explored further) |
| ONE (Ocean Network Express) | `one-line.com/en/services/demurrage-and-detention` | HTTP 404 |

Most major carrier sites return 403 to a plain `curl` fetch (bot/WAF
protection) even with a browser User-Agent — consistent with them being
JS-rendered SPAs, not evidence that no specimen exists on those domains.
**UNTESTED, not "gated":** a real browser session (not available in this
sandbox) might reach content curl cannot.

## Freight-forwarder / auditor blog posts — checked, no invoice asset found

| Page | Status | Finding |
|---|---|---|
| `invoicedataextraction.com/blog/demurrage-detention-invoice-processing` | 200 | JS-rendered app shell; no invoice image/PDF in the static HTML fetched |
| a freight-audit SaaS vendor FAQ page | 200 | Same — marketing site is JS-rendered, only icons in static HTML |
| an ocean-freight-audit firm service page | 200 | Same |
| `gocubic.io/guides/.../demurrage-detention-dispute-playbook-2026` | 200 | Same |
| `flexport.com/blog/demurrage-and-detention-guide/` | 404 | Page does not exist at guessed URL |
| `freightright.com/blog/how-to-read-your-demurrage-invoice` | 404 | Page does not exist at guessed URL |
| `freightos.com/freight-resources/demurrage-meaning-fees-and-charges/` | 200 | Fetched; not mined for images within budget |

## FMC reading room — broader docket search

- `https://www2.fmc.gov/readingroom/proceeding/CC-002/` (200) lists 12
  documents (Order, notices of appearance, motions, briefs, final order).
  All 12 were fetched (200, all PDF). Only the Order to Show Cause
  (135094) states invoice-level facts; the rest are procedural motions or
  legal briefs. None attaches a viewable invoice exhibit — see above.
- Other known FMC enforcement matters (ONE/Wan Hai 2023 civil penalties,
  Hapag-Lloyd 2022 settlement) were **not** re-fetched for this corpus;
  they predate Part 541 and concern
  46 CFR 545.5 "unreasonable practice" findings, not invoice content, and
  their press releases (already fetched 200 in the channel package) do not
  attach invoice exhibits either.

## Search engines — did not surface direct PDF links

- Bing's non-JS RSS search endpoint (`bing.com/search?format=rss&q=...`)
  responds 200 but ignores `filetype:pdf` and `"phrase"` operators in this
  mode and returns generic glossary/dictionary/homepage results for every
  query tried (5 queries: Hapag-Lloyd, Maersk, CMA CGM, `site:fmc.gov`,
  ONE). Not usable for targeted PDF discovery.
- DuckDuckGo's HTML endpoint (`html.duckduckgo.com/html/`) returned HTTP
  202 (bot-check) with no results extractable.
- Google returned HTTP 200 but no `/url?q=` result links were present in
  the static HTML fetched (JS-rendered SERP, consistent with Google's
  known bot mitigation) — **UNTESTED with a real browser**.

## Honest conclusion

The corpus in this directory is **one real regulatory PDF plus one
real-case-derived text record**, not the 15 invoice PDFs a full build would
want. This is reported as a genuine, tested sourcing gap: FMC docket
exhibits are filed confidentially; carrier sites block plain HTTP fetches;
blog/marketing pages are JS-rendered with no static invoice asset; and the
search engines reachable from this sandbox without a real browser session do
not support targeted PDF discovery. `MEASURED.md` reports numbers for **N=1**
and states this explicitly rather than extrapolating from it.
