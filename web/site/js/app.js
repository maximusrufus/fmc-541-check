// Page logic only. Not one rule, citation, day count or letter sentence is computed here --
// every one of them comes back from the demurragedesk Python package running in the worker.
// If you are looking for the screening logic, it is in ../../../demurragedesk/, and the browser
// runs that source directly.

const $ = (id) => document.getElementById(id);

const worker = new Worker(new URL("./engine-worker.js", import.meta.url), { type: "module" });
const pending = new Map();
let nextId = 1;

worker.onmessage = (ev) => {
  const { type, id, data, error, stage, detail, sha } = ev.data || {};
  if (type === "progress") {
    $("engine-status").textContent = `Rules engine: ${detail || stage}…`;
    return;
  }
  const slot = pending.get(id);
  if (!slot) return;
  pending.delete(id);
  if (type === "error") slot.reject(new Error(error));
  else slot.resolve(type === "ready" ? { sha } : data);
};
worker.onerror = (e) => {
  $("engine-status").textContent = "Rules engine failed to start.";
  showError($("form-error"), e.message || "the rules engine could not start");
};

function ask(type, extra = {}) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ type, id, ...extra });
  });
}

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = false;
}
function clearError(el) {
  el.textContent = "";
  el.hidden = true;
}

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

// ---------------------------------------------------------------------------
// Form construction, driven entirely by the rule table
// ---------------------------------------------------------------------------

let catalog = null;

const GROUP_ORDER = ["identifying", "timing", "rate", "dispute", "certification"];

function renderElements(elements) {
  const host = $("elements");
  const previous = collectElementStates();
  host.textContent = "";

  const byGroup = new Map();
  for (const e of elements) {
    if (!byGroup.has(e.group)) byGroup.set(e.group, []);
    byGroup.get(e.group).push(e);
  }
  for (const group of GROUP_ORDER) {
    const items = byGroup.get(group);
    if (!items) continue;
    const wrap = el("div", "group");
    wrap.appendChild(el("p", "group-lead", items[0].group_lead));
    for (const item of items) {
      const row = el("div", "element");
      row.dataset.key = item.key;
      const left = el("div", "text");
      left.appendChild(document.createTextNode(item.text));
      left.appendChild(el("span", "cite", item.cite));
      row.appendChild(left);

      const choices = el("div", "choices");
      for (const [value, label] of [["present", "on the invoice"], ["absent", "missing"], ["unsure", "not sure"]]) {
        const lab = el("label");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `el:${item.key}`;
        input.value = value;
        // Default is "not sure": the page never assumes an element is missing.
        input.checked = (previous[item.key] || "unsure") === value;
        lab.appendChild(input);
        lab.appendChild(document.createTextNode(label));
        choices.appendChild(lab);
      }
      row.appendChild(choices);
      wrap.appendChild(row);
    }
    host.appendChild(wrap);
  }
}

function collectElementStates() {
  const out = {};
  for (const row of document.querySelectorAll("#elements .element")) {
    const key = row.dataset.key;
    const picked = row.querySelector("input:checked");
    out[key] = picked ? picked.value : "unsure";
  }
  return out;
}

function renderFacts(facts) {
  const host = $("facts");
  host.textContent = "";
  for (const f of facts) {
    const row = el("div", "fact");
    row.dataset.field = f.fact_field;

    const q = el("label", "q");
    q.setAttribute("for", `fact:${f.fact_field}`);
    q.textContent = f.label;
    row.appendChild(q);

    if (f.kind === "bool") {
      const sel = document.createElement("select");
      sel.id = `fact:${f.fact_field}`;
      for (const [v, t] of [["", "not answered"], ["yes", "yes"], ["no", "no"]]) {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = t;
        sel.appendChild(o);
      }
      row.appendChild(sel);
    } else {
      const input = document.createElement("input");
      input.type = "text";
      input.id = `fact:${f.fact_field}`;
      input.placeholder = "dates, e.g. 2026-03-08, 2026-03-09 — leave blank if not asserting";
      row.appendChild(input);
    }
    row.appendChild(el("span", "ev", `You must be able to produce: ${f.evidence}`));
    if (!f.enumerated) {
      row.appendChild(
        el("span", "notenum", `Not an enumerated 545.5 factor — raised under ${f.cite}.`),
      );
    }
    host.appendChild(row);
  }
}

function collectFacts() {
  const out = {};
  for (const row of document.querySelectorAll("#facts .fact")) {
    const field = row.dataset.field;
    const input = row.querySelector("input, select");
    const value = (input && input.value.trim()) || "";
    if (value !== "") out[field] = value;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Payload
// ---------------------------------------------------------------------------

const FIELDS = [
  "invoice_id", "charge_last_incurred", "invoice_issue_date", "charge_first_incurred",
  "billing_party_type", "upstream_invoice_issue_date", "billing_party", "billed_party",
  "billed_party_role", "direction", "total_amount", "daily_rate", "charged_dates",
  "stated_dispute_window_days", "container_number", "bill_of_lading",
];

function buildPayload() {
  const payload = { elements: collectElementStates(), facts: collectFacts() };
  for (const name of FIELDS) {
    const node = $(name);
    if (node) payload[name] = node.value.trim();
  }
  return payload;
}

// ---------------------------------------------------------------------------
// Rendering a result
// ---------------------------------------------------------------------------

const BADGE = { UNPAYABLE: "unpayable", DISPUTABLE: "disputable", "NO DEFECT FOUND": "clean" };

const VERDICT_TEXT = {
  UNPAYABLE:
    "On what you have told us, this invoice carries a defect that 46 CFR part 541 says " +
    "eliminates your obligation to pay the charge. The rule and the arithmetic are below.",
  DISPUTABLE:
    "No defect on the face of the invoice makes this unpayable outright, but there are grounds " +
    "to contest the charge as unreasonable under 46 CFR 545.5 — based only on facts you asserted.",
  "NO DEFECT FOUND":
    "Nothing you told us shows a 46 CFR part 541 billing defect on the face of this invoice. " +
    "That is not the same as saying the charge is correct — see what this cannot tell you, below.",
};

function renderGround(d) {
  const cls = d.consequence === "unpayable" ? "unpayable" : "disputable";
  const box = el("div", `ground ${cls}`);
  const head = el("p");
  head.appendChild(el("span", "cite", d.cite));
  head.appendChild(document.createTextNode(" "));
  head.appendChild(el("span", "consequence", d.consequence));
  box.appendChild(head);

  const quote = el("blockquote");
  quote.textContent = `“${d.rule_text}”`;
  box.appendChild(quote);

  box.appendChild(el("p", null, d.summary));
  if (d.math) box.appendChild(el("p", "math", d.math));
  return box;
}

function renderResult(r) {
  $("verdict-badge").textContent = r.verdict;
  $("verdict-badge").className = `badge ${BADGE[r.verdict]}`;
  $("verdict").textContent = VERDICT_TEXT[r.verdict];
  $("amount-line").textContent = r.amount_at_issue
    ? `Amount on this invoice: $${r.amount_at_issue}. ${r.amount_note}`
    : r.amount_note;

  const grounds = $("grounds");
  grounds.textContent = "";
  const unpayable = r.unpayable_defects || [];
  const disputable = r.disputable_defects || [];
  if (unpayable.length) {
    grounds.appendChild(el("h3", null, "Grounds that make the charge unpayable (46 CFR part 541)"));
    grounds.appendChild(
      el("p", "hint", "These stand on the document alone and need no fact from you."),
    );
    for (const d of unpayable) grounds.appendChild(renderGround(d));
  }
  if (disputable.length) {
    grounds.appendChild(el("h3", null, "Grounds to dispute the charge as unreasonable (46 CFR 545.5)"));
    grounds.appendChild(
      el("p", "hint", "These need facts you can evidence. They are raised in addition to, never instead of, the above."),
    );
    for (const d of disputable) grounds.appendChild(renderGround(d));
  }
  if (!unpayable.length && !disputable.length) {
    grounds.appendChild(el("p", null, "No ground was found on what you supplied."));
  }

  const needs = $("needs-doc");
  needs.textContent = "";
  if ((r.needs_your_document || []).length) {
    needs.appendChild(el("h3", null, "Needs your document"));
    needs.appendChild(
      el("p", "hint",
        `You marked ${r.needs_your_document.length} required element(s) “not sure”. ` +
        "None of them counted against the carrier. Check each against the invoice — if any is " +
        "genuinely missing, 46 CFR 541.5 makes the charge unpayable on that ground alone."),
    );
    const ul = el("ul", "queue");
    for (const q of r.needs_your_document) {
      const li = el("li");
      li.appendChild(document.createTextNode(q.text));
      li.appendChild(el("span", "cite", ` ${q.cite}`));
      ul.appendChild(li);
    }
    needs.appendChild(ul);
  }

  const ev = $("evidence");
  ev.textContent = "";
  if ((r.evidence_needed || []).length) {
    ev.appendChild(el("h3", null, "Facts you have not asserted"));
    ev.appendChild(
      el("p", "hint",
        "These 46 CFR 545.5 factors are neither alleged nor waived. Supplying the evidence " +
        "listed could add grounds; it cannot affect anything above."),
    );
    const ul = el("ul", "queue");
    for (const g of r.evidence_needed) {
      ul.appendChild(el("li", null, `${g.label} (${g.cite}) — needs: ${g.evidence}`));
    }
    ev.appendChild(ul);
  }

  $("self-help").textContent = r.self_help_note;
  $("scope-note").textContent = r.scope_note;
  $("letter").textContent = r.letter;
  $("results").hidden = false;
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

async function refreshCatalog() {
  catalog = await ask("catalog", { direction: $("direction").value });
  renderElements(catalog.elements);
  renderFacts(catalog.facts);
  const p = catalog.provenance;
  $("provenance").textContent =
    `Rules retrieved ${p.retrieved} from ${p.sources.length} primary sources; ` +
    `${Object.keys(p.rules).length} encoded provisions, ${p.unverified.length} unverified.`;
}

async function boot() {
  try {
    const { sha } = await ask("ready");
    $("engine-status").textContent = "Rules engine: ready, running locally in your browser.";
    $("engine-sha").textContent = sha.slice(0, 16);
    await refreshCatalog();
    $("run").disabled = false;
    $("csv-run").disabled = false;
    document.body.dataset.engine = "ready";
  } catch (err) {
    $("engine-status").textContent = `Rules engine: failed — ${err.message}`;
    document.body.dataset.engine = "failed";
  }
}

$("run").disabled = true;
$("csv-run").disabled = true;

$("direction").addEventListener("change", () => {
  if (catalog) refreshCatalog().catch((e) => showError($("form-error"), e.message));
});

$("billing_party_type").addEventListener("change", (e) => {
  $("upstream-wrap").hidden = e.target.value !== "nvocc";
});

$("invoice-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError($("form-error"));
  if (!$("charge_last_incurred").value || !$("invoice_issue_date").value) {
    showError($("form-error"), "Both dates are required: when the charge was last incurred, and when the invoice was issued.");
    return;
  }
  $("run").disabled = true;
  try {
    renderResult(await ask("screen", { payload: buildPayload() }));
  } catch (err) {
    showError($("form-error"), err.message);
  } finally {
    $("run").disabled = false;
  }
});

$("clear").addEventListener("click", () => {
  $("invoice-form").reset();
  $("upstream-wrap").hidden = true;
  $("results").hidden = true;
  clearError($("form-error"));
  if (catalog) renderElements(catalog.elements);
});

$("copy-letter").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("letter").textContent);
    $("copy-status").textContent = "Copied.";
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("letter"));
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    $("copy-status").textContent = "Selected — press Ctrl+C to copy.";
  }
});

$("csv-run").addEventListener("click", async () => {
  clearError($("csv-error"));
  const file = $("csv-file").files && $("csv-file").files[0];
  if (!file) {
    showError($("csv-error"), "Choose a CSV file first.");
    return;
  }
  $("csv-run").disabled = true;
  try {
    // Read in the page; the file is never uploaded.
    const text = await file.text();
    const data = await ask("csv", { text });
    const tbody = $("csv-table").querySelector("tbody");
    tbody.textContent = "";
    for (const r of data.results) {
      const tr = el("tr");
      tr.appendChild(el("td", null, r.invoice_id));
      const vd = el("td");
      vd.appendChild(el("span", `badge ${BADGE[r.verdict]}`, r.verdict));
      tr.appendChild(vd);
      const first = (r.unpayable_defects[0] || r.disputable_defects[0] || {}).cite || "—";
      tr.appendChild(el("td", null, first));
      tr.appendChild(el("td", null, r.amount_at_issue ? `$${r.amount_at_issue}` : "—"));
      tbody.appendChild(tr);
    }
    const c = data.counts;
    $("csv-counts").textContent =
      `${data.results.length} invoice(s) screened: ${c.UNPAYABLE} unpayable, ` +
      `${c.DISPUTABLE} disputable, ${c["NO DEFECT FOUND"]} with no defect found. ` +
      "Amounts shown are the ones in your file, echoed back; no total is asserted.";
    $("csv-errors").textContent = data.errors.length
      ? `${data.errors.length} row(s) could not be screened and were skipped, not guessed: ` +
        data.errors.map((e) => `line ${e.line}`).join(", ")
      : "";
    $("csv-results").hidden = false;
  } catch (err) {
    showError($("csv-error"), err.message);
  } finally {
    $("csv-run").disabled = false;
  }
});

boot();
