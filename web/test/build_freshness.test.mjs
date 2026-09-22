// Guards the single-source-of-truth claim at the build boundary.
//
// The browser imports the demurragedesk package itself, so there is no JS port to drift. What CAN
// drift is the committed *bundle*: edit demurragedesk/rules.py, forget to rebuild, and the page
// quietly serves yesterday's rules. These tests fail when that happens.
//
// The JS-vs-Python verdict comparison is the e2e parity spec (e2e/tests/parity.spec.mjs), which
// replays the same fixtures through the real browser engine.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(join(dirname(fileURLToPath(import.meta.url)), ".."));
const REPO = resolve(join(WEB, ".."));
const PY = process.env.PYTHON || "C:\\Python314\\python.exe";
const PARITY = join(WEB, "e2e", "fixtures", "parity.json");

function python(args, opts = {}) {
  return execFileSync(PY, args, { cwd: WEB, encoding: "utf8", ...opts });
}

test("the served bundle matches the Python source (scripts/build_engine.py --check)", () => {
  // Non-zero exit = site/py/demurragedesk.zip, its .sha256, or js/engine-pin.js is stale.
  const out = python([join("scripts", "build_engine.py"), "--check"]);
  assert.match(out, /engine bundle is current/);
});

test("the served sha256 and the compiled pin agree with the zip on disk", async () => {
  const { createHash } = await import("node:crypto");
  const zip = readFileSync(join(WEB, "site", "py", "demurragedesk.zip"));
  const sha = createHash("sha256").update(zip).digest("hex");
  const shaFile = readFileSync(join(WEB, "site", "py", "demurragedesk.sha256"), "utf8").trim();
  const pin = readFileSync(join(WEB, "site", "js", "engine-pin.js"), "utf8");

  assert.equal(shaFile.split(/\s+/)[0], sha, "demurragedesk.sha256 does not match the zip");
  assert.ok(pin.includes(sha), "engine-pin.js does not carry the zip's hash");
});

test("the bundle contains only the package and its one adapter", async () => {
  // A top-level decimal.py or json.py in the bundle would shadow the stdlib inside Pyodide.
  const names = python([
    "-c",
    "import sys,zipfile;print('\\n'.join(sorted(zipfile.ZipFile(sys.argv[1]).namelist())))",
    join(WEB, "site", "py", "demurragedesk.zip"),
  ])
    .trim()
    .split(/\r?\n/);

  assert.ok(names.includes("demurragedesk/rules.py"), "rules.py is not in the bundle");
  assert.ok(names.includes("demurragedesk/screen.py"), "screen.py is not in the bundle");
  assert.ok(names.includes("webapi.py"), "the adapter is not in the bundle");
  for (const n of names) {
    assert.ok(
      n === "webapi.py" || n.startsWith("demurragedesk/"),
      `bundle entry ${n} would shadow the stdlib`,
    );
  }
});

test("parity fixtures still match what the Python package produces today", () => {
  assert.ok(existsSync(PARITY), "run: npm run fixtures");
  const program = [
    "import json,sys",
    "sys.path.insert(0, sys.argv[1])",
    "sys.path.insert(0, sys.argv[2])",
    "import webapi",
    "data = json.load(open(sys.argv[3], encoding='utf-8'))",
    "bad = []",
    "for c in data['cases']:",
    "    if webapi.screen_payload(dict(c['payload'])) != c['expected']:",
    "        bad.append(c['name'])",
    "cc = data['csv_case']",
    "if webapi.screen_csv(cc['text'], cc['today']) != cc['expected']:",
    "    bad.append('csv_batch')",
    "print(json.dumps(bad))",
  ].join("\n");

  const out = python(["-c", program, REPO, join(WEB, "py"), PARITY]);
  const stale = JSON.parse(out.trim().split(/\r?\n/).pop());
  assert.deepEqual(
    stale,
    [],
    `parity fixtures are stale for: ${stale.join(", ")} -- run: npm run fixtures`,
  );
});

test("every rule the page can quote was retrieved verbatim", () => {
  const out = python([
    "-c",
    "import sys,json;sys.path.insert(0,sys.argv[1]);from demurragedesk import provenance;print(json.dumps(provenance()['unverified']))",
    REPO,
  ]);
  assert.deepEqual(JSON.parse(out.trim()), [], "an encoded rule is UNVERIFIED");
});
