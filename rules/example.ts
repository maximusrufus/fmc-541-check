// Minimal, dependency-free usage example for rules/fmc-541.json.
// Run with: npx tsx rules/example.ts   (or compile with tsc)
import { readFileSync } from "node:fs";
import type { FmcRulesDocument } from "./fmc-541.d.ts";

const rules: FmcRulesDocument = JSON.parse(
  readFileSync(new URL("./fmc-541.json", import.meta.url), "utf-8"),
);

function addDays(d: Date, n: number): Date {
  const out = new Date(d.getTime());
  out.setUTCDate(out.getUTCDate() + n);
  return out;
}

// 541.7(a): carrier's clock runs from when the charge was last incurred.
// 541.7(b): NVOCC's clock runs from the date it received the upstream invoice.
export function invoiceDeadline(
  lastIncurred: Date,
  kind: "carrier" | "nvocc",
  receivedOn?: Date,
): Date {
  const cite = kind === "carrier" ? "46 CFR 541.7(a)" : "46 CFR 541.7(b)";
  const clock = rules.clocks.find((c) => c.cite === cite);
  if (!clock) throw new Error(`clock not found: ${cite}`);
  const anchor = kind === "carrier" ? lastIncurred : (receivedOn ?? lastIncurred);
  return addDays(anchor, clock.days);
}

// Returns the 541.6 elements missing from a parsed invoice's field map for
// the given direction (elements not applicable to that direction are skipped).
export function missingElements(
  invoice: Record<string, unknown>,
  direction: "import" | "export",
): string[] {
  return rules.elements
    .filter((e) => e.field && e.applies_to.includes(direction))
    .filter((e) => invoice[e.field] === undefined || invoice[e.field] === null || invoice[e.field] === "")
    .map((e) => e.key);
}
