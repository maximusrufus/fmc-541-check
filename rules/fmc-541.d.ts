/**
 * Type declarations for rules/fmc-541.json.
 *
 * This file declares types only -- no runtime code, no dependencies. Import
 * the JSON directly (e.g. via `import data from "./fmc-541.json"` with
 * `resolveJsonModule` on, or `JSON.parse(readFileSync(...))`) and cast it to
 * `FmcRulesDocument` if your build doesn't infer JSON module types.
 *
 * Never hand-edit fmc-541.json -- it is generated from the Python package.
 * See rules/README.md.
 */

/** How a quoted string's provenance was checked. */
export type Verified =
  | "VERBATIM"
  | "VACATED"
  | "UNVERIFIED"
  | "VERBATIM_UPSTREAM";

export type Direction = "import" | "export";

export type ElementGroup =
  | "identifying"
  | "timing"
  | "rate"
  | "dispute"
  | "certification";

/** One minimum-content item required by 46 CFR 541.6. */
export interface FmcElement {
  /** e.g. "541.6(b)(4)" */
  key: string;
  group: ElementGroup;
  /** Verbatim regulatory text of the item. */
  text: string;
  verified: Verified;
  /** Which invoice direction(s) this element applies to. */
  applies_to: Direction[];
  /** Short machine-friendly field name, e.g. "invoice_date". Empty string if none. */
  field: string;
}

/** One 30-day (or similar) deadline defined in 46 CFR 541.7/541.8. */
export interface FmcClock {
  /** e.g. "46 CFR 541.7(a)" */
  cite: string;
  /** What the clock runs from, e.g. "date the charge was last incurred". */
  trigger: string;
  days: number;
  day_type: "calendar";
  /** Short descriptive heading naming the clock/who it governs. */
  who: string;
  /** Verbatim regulatory text. */
  text: string;
  verified: Verified;
}

/** 46 CFR 541.5 -- consequence of a missing required element or late invoice. */
export interface FmcConsequence {
  cite: string;
  heading: string;
  text: string;
  verified: Verified;
}

/** One factor the Commission weighs under 46 CFR 545.5's incentive principle. */
export interface FmcFactor545_5 {
  /** e.g. "545.5(c)(2)(i)" or "545.5(c)(1), (f)" for non-enumerated factors. */
  key: string;
  label: string;
  text: string;
  /** Field name used to carry a tri-state (yes/no/unknown) fact for this factor. */
  fact_field: string;
  /** What the billed party would need to produce to assert this factor. */
  evidence: string;
  /** True only if 545.5 itself names this factor; false if reached via (c)(1)+(f). */
  enumerated: boolean;
  verified: Verified;
}

export interface FmcProvenance {
  retrieved: string;
  sources: string[];
  rules: Record<string, Verified>;
  unverified: string[];
  vacated: string[];
}

export interface FmcRulesDocument {
  schema_version: number;
  generated_from: {
    package_version: string;
    retrieved: string;
    sources: string[];
  };
  elements: FmcElement[];
  clocks: FmcClock[];
  consequences: FmcConsequence[];
  factors_545_5: FmcFactor545_5[];
  /** Citations checked and found withdrawn ("[Reserved]"); never enforced. */
  vacated: string[];
  provenance: FmcProvenance;
}
