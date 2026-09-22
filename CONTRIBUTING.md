# Contributing

- **Rule-text changes must cite eCFR (or another primary source) with a
  retrieval date.** `demurragedesk/rules.py` quotes the regulation verbatim;
  a PR that changes a quoted rule string needs the eCFR versioner URL
  (`https://www.ecfr.gov/api/versioner/v1/full/<date>/title-46.xml?part=<n>`)
  or govinfo XML it was checked against, plus the date you checked it.
  Unsourced rule-text edits will be asked to add a citation before merge.
- **Tests required.** Every behavior change needs a passing test in
  `tests/`. Run `python -m pytest -q` before opening a PR.
- **Carrier invoice layouts:** if `demurragedesk.ingest` misreads a real
  carrier invoice, open an issue with a **redacted** sample (strip account
  numbers, container numbers, dollar amounts if you want, and any personal
  data) showing the field label/layout that didn't parse. A redacted sample
  is far more useful than a description.
- **The web bundle is generated, never hand-edited.** `web/site/py/*` and
  `web/site/js/engine-pin.js` are produced by
  `python web/scripts/build_engine.py`. If you change `demurragedesk/*.py`,
  regenerate before committing: `python web/scripts/build_engine.py`, and
  verify with `python web/scripts/build_engine.py --check`.
- **No paid dependencies, ever.** `pyproject.toml` optional `ocr` extra is
  CPU-only, local, free (`rapidocr-onnxruntime` + `pymupdf`). Do not add a
  dependency that requires a paid API key or cloud service.
