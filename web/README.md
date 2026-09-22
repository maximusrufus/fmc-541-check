# DemurrageDesk — the self-check page

A static page that lets an importer screen its own ocean demurrage/detention
invoice against 46 CFR part 541, in the browser, with nothing uploaded.

The pitch is one fact, and it is the regulation's own: an invoice issued more
than **30 calendar days** after the charge was last incurred is one
*"the billed party is not required to pay"* (541.7), and omitting **any**
required element independently *"eliminates any obligation of the billed party
to pay the applicable charge"* (541.5). Importers are already holding these
invoices. This page lets them find out for themselves.

## One source of truth for the rules

**The browser runs the `demurragedesk` Python package itself, under Pyodide.**
There is no JavaScript implementation of part 541 anywhere in this project, so
there is nothing for a port to drift away from.

This was the simpler of the two options in the brief, and it is simpler for a
reason that is specific to this package rather than a general preference:

* Compiling the rule *table* to JSON would have moved the quoted text across,
  but not the **logic** — the 541.7(a)-vs-541.7(b) anchor switch, the
  inclusive-day-30 boundary, the tri-state 545.5 fact model where unknown is
  neither yes nor no, the overlap arithmetic, and the whole 541.8 letter
  renderer. All of that would have had to be rewritten in JS and then policed
  by a parity test forever. That is the divergence risk the brief warns about,
  and it is real: `screen.py` has seven checks and `packet.py` builds a
  ~5,800-character letter.
* The package makes this cheap: it imports **only the Python standard library**
  at module scope. `reportlab` and `pypdf` are lazy imports inside
  `write_pdf()` / `read_pdf_invoice()`, which the web build never calls. So the
  bundle is 34 KB of pure Python and needs no wheels.
* Pyodide was already vendored and CSP-proven next door in PFICWeb, including
  the `'wasm-unsafe-eval'` allowance and a Web Worker that makes no network
  call of its own.

The cost is honest: ~13 MB of Pyodide and a few seconds of first load. For a
page whose entire promise is *"we can't see your invoice"*, that is the right
trade — and it buys the letter text, the CSV ingest and the provenance report
for free, all from the same source.

### How it is bundled

```
scripts/build_engine.py            # the ONLY producer of the served bundle
  -> site/py/demurragedesk.zip     # demurragedesk/*.py + py/webapi.py, verbatim
  -> site/py/demurragedesk.sha256
  -> site/js/engine-pin.js         # second, independent hash pin
```

The zip is deterministic (sorted entries, fixed timestamps), so
`build_engine.py --check` fails whenever the committed bundle no longer matches
the Python source. The worker refuses to import a bundle unless its SHA-256
matches **both** the served `.sha256` and the compiled-in pin, and unless every
entry lives under `demurragedesk/` or is exactly `webapi.py` (a top-level
`decimal.py` in the zip would shadow the stdlib).

`py/webapi.py` is the single translation layer between the form and the
package. It holds no rule, citation, day count or letter sentence of its own.

## The parity test

Two layers, because they fail for different reasons.

| Test | Runs | Fails when |
|---|---|---|
| `test/build_freshness.test.mjs` | `node --test` | the committed zip/sha/pin is stale, the bundle would shadow the stdlib, `fixtures/parity.json` no longer matches what the Python produces today, or any encoded rule is `UNVERIFIED` |
| `e2e/tests/parity.spec.mjs` | Playwright | the browser's verdict differs from native CPython's on any shared fixture |

`scripts/gen_parity_fixtures.py` writes `e2e/fixtures/parity.json`: 12 payloads
plus a CSV batch, each with the result produced by **native CPython** importing
the package directly. The e2e spec replays every one through the page's own
worker and asserts **deep equality over the whole result object** — verdict,
every defect with its citation, rule text and arithmetic, the evidence gaps,
the deadlines, and the full letter text, character for character. A divergence
there means a stale bundle, a broken unpack, or an Emscripten behaviour change
— never a hand-port bug, because there is no hand port.

## What the page refuses to claim

These are enforced in `py/webapi.py` and asserted in the e2e suite, not merely
written in the copy:

* **It never states a recoverable figure the user did not supply.** The only
  money shown is money the user typed, echoed back and labelled as an echo. No
  totals, no extrapolation, no "you could recover ~$X".
* **"Not sure" never becomes a defect.** An element marked unsure is passed to
  the screen as *present*, so it cannot manufacture a 541.5 ground, and is
  surfaced separately as "needs your document". Unsure is the default for every
  element, so a user who fills in nothing gets no accusations.
* **Unasserted 545.5 facts stay unasserted** — neither alleged nor waived —
  and render as evidence gaps listing what the user would have to produce.
* **It says plainly that it reads the face of the invoice only**, and cannot
  verify free time, the daily rate or tariff terms against a service contract
  it has never seen. "No defect found" is never rendered as "the charge is
  correct".
* **The free path is stated before the paid one.** The 541.8 letter is right
  there to copy, with a line saying the user may send it themselves for free
  and needs no licence or lawyer. The contingency offer sits below it.

CSV note: the batch path uses the package's own ingest doctrine, where a column
your export lacks is an element the invoice *omits*. The page says so, because
that doctrine is right for a paper invoice and wrong for a thin CSV.

## Privacy posture

`site/_headers` ships `default-src 'self'` with `connect-src 'self'`,
`object-src 'none'`, `base-uri 'none'`, `form-action 'none'` and
`frame-ancestors 'none'`. Every asset is self-hosted; there are no third-party
origins and no analytics. `scripts/serve.mjs` applies the same `_headers`
locally, so the CSP under test is the shipped one.

The e2e network audit records every request the browser makes — including from
inside the worker — and asserts they are all same-origin GETs with empty
bodies, and that none carries the invoice number, container number or company
name the test typed in. It first asserts that the Pyodide wasm and the rules
zip *were* captured, so the audit cannot pass vacuously.

## Commands

```bash
npm run build          # rebuild site/py/demurragedesk.zip + sha + pin
npm run build:check    # CI: fail if the bundle is stale
npm run fixtures       # regenerate e2e/fixtures/parity.json from native Python
npm test               # node --test: bundle freshness + fixture freshness
npm run serve          # http://127.0.0.1:5189
npm run test:e2e       # Playwright, system Chrome, port 5189
```

After editing anything in `../demurragedesk/` or `py/webapi.py`, run
`npm run build && npm run fixtures`, or the freshness tests will fail — which
is the point.

Not legal advice.
