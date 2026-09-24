"""Export the encoded 46 CFR part 541/545 rules as a single JSON document.

This is the cross-language interop surface: every string that matters is
pulled directly from the same objects ``demurragedesk.screen`` imports and
runs against invoices -- nothing here is retyped, so the JSON can never drift
from the Python engine's actual behavior.

Regenerate with::

    python -m demurragedesk.export_rules --out rules/fmc-541.json

Never hand-edit the output file; edit ``rules.py`` and regenerate instead.
``tests/test_export_rules.py`` fails the committed copy against a fresh
``export()`` call so drift is caught in CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .rules import (
    CLOCKS,
    FACTORS_545_5,
    REQUIRED_ELEMENTS,
    RETRIEVED,
    RULE_541_5,
    SOURCES,
    provenance,
)

#: Bump when the shape of the exported document changes in a
#: backward-incompatible way (key removed/renamed, type changed).
SCHEMA_VERSION = 1

#: Sections retrieved and checked, found withdrawn ("[Reserved]"), and never
#: enforced.  Kept in sync with ``rules.provenance()['vacated']`` by
#: ``test_export_rules.py``.
VACATED_SECTIONS = ("46 CFR 541.4", "46 CFR 502.303")


def export() -> dict:
    """Build the single-document JSON export of the rules engine.

    Every ``text`` field below is the *same string object* the Python engine
    (``screen.py``) checks invoices against -- this function imports the
    dataclass instances from ``rules.py`` and reads their attributes, it
    never retypes a citation or a quoted sentence.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from": {
            "package_version": __version__,
            "retrieved": RETRIEVED,
            "sources": list(SOURCES),
        },
        "elements": [
            {
                "key": e.key,
                "group": e.group,
                "text": e.text,
                "verified": e.verified,
                "applies_to": list(e.applies_to),
                "field": e.field_name,
            }
            for e in REQUIRED_ELEMENTS
        ],
        "clocks": [
            {
                "cite": c.cite,
                "trigger": c.anchor,
                "days": c.days,
                "day_type": "calendar",
                # "who": the clock's short descriptive heading from rules.py
                # (e.g. "NVOCC re-billing window") -- rules.py has no
                # separate structured "bound party" field, so this is the
                # closest verbatim-sourced description of who/what the
                # clock governs. See rules/README.md.
                "who": c.heading,
                "text": c.text,
                "verified": c.verified,
            }
            for c in CLOCKS.values()
        ],
        "consequences": [
            {
                "cite": RULE_541_5["cite"],
                "heading": RULE_541_5["heading"],
                "text": RULE_541_5["text"],
                "verified": RULE_541_5["verified"],
            }
        ],
        "factors_545_5": [
            {
                "key": f.key,
                "label": f.label,
                "text": f.text,
                "fact_field": f.fact_field,
                "evidence": f.evidence,
                "enumerated": f.enumerated,
                "verified": f.verified,
            }
            for f in FACTORS_545_5
        ],
        "vacated": list(VACATED_SECTIONS),
        "provenance": provenance(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export demurragedesk's rules as a single JSON document."
    )
    parser.add_argument(
        "--out",
        default="-",
        help="output path, or '-' for stdout (default: stdout)",
    )
    args = parser.parse_args(argv)

    doc = export()
    text = json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    if args.out == "-":
        print(text, end="")
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
