// Module Web Worker: loads self-hosted Pyodide and the demurragedesk bundle, then runs the
// package's OWN screening code. Nothing here reimplements a rule; every verdict, citation and
// day count is computed by the Python in demurragedesk.zip.
//
// Invoice details arrive by postMessage and never leave this worker except as the computed
// result posted back to the page. There is no network call to anything but same-origin static
// assets, and the CSP (connect-src 'self') is what enforces that rather than good intentions.
import { loadPyodide } from "../vendor/pyodide/pyodide.mjs";
import { ENGINE_SHA256 } from "./engine-pin.js";

const PY_DIR = new URL("../py/", import.meta.url);
const VENDOR = new URL("../vendor/pyodide/", import.meta.url);

let enginePromise = null;

const progress = (stage, detail = "") => postMessage({ type: "progress", stage, detail });

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchStrict(url) {
  const res = await fetch(url, { cache: "no-cache", credentials: "omit" });
  if (!res.ok) throw new Error(`could not load ${url} (HTTP ${res.status})`);
  return res;
}

async function loadBundle(py) {
  progress("engine", "verifying the rules bundle");
  const zip = new Uint8Array(await (await fetchStrict(new URL("demurragedesk.zip", PY_DIR))).arrayBuffer());

  // A host that answers a missing path with an HTML page is caught by the zip magic bytes,
  // never by HTTP status alone.
  if (!(zip.length > 4 && zip[0] === 0x50 && zip[1] === 0x4b)) {
    throw new Error("demurragedesk.zip is not a zip archive; refusing to import it.");
  }

  const shaText = (await (await fetchStrict(new URL("demurragedesk.sha256", PY_DIR))).text()).trim();
  const m = shaText.match(/^([0-9a-fA-F]{64})\b/);
  if (!m) throw new Error("demurragedesk.sha256 is missing or malformed; refusing to import the bundle.");

  const got = hex(await crypto.subtle.digest("SHA-256", zip));
  if (got !== m[1].toLowerCase()) {
    throw new Error(`Rules bundle sha256 mismatch (expected ${m[1].toLowerCase()}, got ${got}); refusing to import it.`);
  }
  // Second, independent pin compiled into engine-pin.js by scripts/build_engine.py. Defends
  // against a swapped zip served with a matching .sha256. It does not defend against a fully
  // compromised origin; the external check is comparing this hash against the repository.
  if (got !== String(ENGINE_SHA256).toLowerCase()) {
    throw new Error(`Rules bundle does not match the pinned hash (pinned ${ENGINE_SHA256}, got ${got}); refusing to import it.`);
  }

  // Stdlib-shadowing guard: every entry must be the package or the single adapter module.
  py.globals.set("_dd_zip", zip);
  const bad = py.runPython(
    [
      "import io, zipfile",
      "_n = zipfile.ZipFile(io.BytesIO(_dd_zip.to_py())).namelist()",
      "_b = [x for x in _n if ('..' in x.split('/')) or not (x.startswith('demurragedesk/') or x == 'webapi.py')]",
      "del _dd_zip",
      "', '.join(_b[:5])",
    ].join("\n"),
  );
  if (bad) throw new Error(`Rules bundle contains unexpected entries (${bad}); refusing to import it.`);

  py.FS.mkdirTree("/engine");
  py.unpackArchive(zip.buffer, "zip", { extractDir: "/engine" });
  py.runPython("import sys\nif '/engine' not in sys.path: sys.path.insert(0, '/engine')");

  progress("engine", "loading the 46 CFR part 541 rules");
  py.runPython(
    [
      "import json",
      "import webapi",
      "def _dd_screen(s):",
      "    return json.dumps(webapi.screen_payload(json.loads(s)))",
      "def _dd_csv(text, today):",
      "    return json.dumps(webapi.screen_csv(text, today or None))",
      "def _dd_catalog(direction):",
      "    return json.dumps({",
      "        'elements': webapi.element_catalog(direction),",
      "        'facts': webapi.fact_catalog(),",
      "        'provenance': webapi.provenance(),",
      "        'scope_note': webapi.SCOPE_NOTE,",
      "        'self_help_note': webapi.SELF_HELP_NOTE,",
      "    })",
    ].join("\n"),
  );
  return {
    sha: got,
    screen: py.globals.get("_dd_screen"),
    csv: py.globals.get("_dd_csv"),
    catalog: py.globals.get("_dd_catalog"),
  };
}

function engine() {
  if (!enginePromise) {
    enginePromise = (async () => {
      progress("engine", "starting the Python runtime");
      const py = await loadPyodide({ indexURL: VENDOR.href });
      return await loadBundle(py);
    })().catch((err) => {
      enginePromise = null; // a failed load must not poison every later attempt
      throw err;
    });
  }
  return enginePromise;
}

self.onmessage = async (ev) => {
  const { type, id } = ev.data || {};
  try {
    const eng = await engine();
    if (type === "ready") {
      postMessage({ type: "ready", id, sha: eng.sha });
    } else if (type === "catalog") {
      postMessage({ type: "result", id, data: JSON.parse(eng.catalog(ev.data.direction || "import")) });
    } else if (type === "screen") {
      postMessage({ type: "result", id, data: JSON.parse(eng.screen(JSON.stringify(ev.data.payload))) });
    } else if (type === "csv") {
      postMessage({ type: "result", id, data: JSON.parse(eng.csv(ev.data.text, ev.data.today || "")) });
    } else {
      throw new Error(`unknown request ${type}`);
    }
  } catch (err) {
    postMessage({ type: "error", id, error: String((err && err.message) || err) });
  }
};
