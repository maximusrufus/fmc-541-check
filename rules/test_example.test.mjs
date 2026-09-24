// Node test for rules/example.ts. Run with: node --test rules/
// Node 22.6+/24 strips TypeScript types natively for plain-syntax .ts files
// (no --experimental-strip-types flag needed as of this repo's Node 24).
import test from "node:test";
import assert from "node:assert/strict";
import { invoiceDeadline, missingElements } from "./example.ts";

test("carrier deadline is last-incurred + 30 calendar days", () => {
  const lastIncurred = new Date("2026-01-01T00:00:00Z");
  const deadline = invoiceDeadline(lastIncurred, "carrier");
  assert.equal(deadline.toISOString().slice(0, 10), "2026-01-31");
});

test("NVOCC deadline is received + 30 calendar days, not last-incurred", () => {
  const lastIncurred = new Date("2026-01-01T00:00:00Z");
  const receivedOn = new Date("2026-02-10T00:00:00Z");
  const deadline = invoiceDeadline(lastIncurred, "nvocc", receivedOn);
  assert.equal(deadline.toISOString().slice(0, 10), "2026-03-12");
});

test("missingElements flags absent import-only fields and skips export-only ones", () => {
  const invoice = {
    bill_of_lading: "BOL123",
    container_number: "CONT456",
    // port_of_discharge deliberately omitted (import-only, required)
    invoice_date: "2026-01-05",
  };
  const missing = missingElements(invoice, "import");
  assert.ok(missing.includes("541.6(a)(3)")); // port of discharge
  assert.ok(!missing.includes("541.6(a)(1)")); // bill of lading present
  assert.ok(!missing.includes("541.6(a)(2)")); // container number present

  const missingExport = missingElements(invoice, "export");
  assert.ok(!missingExport.includes("541.6(a)(3)")); // not applicable to export
});
