#!/usr/bin/env node
// Tiny local static server for site/ that applies site/_headers, so the CSP is enforced locally
// exactly as it would be on a static host -- including for the Web Worker that runs Pyodide.
// Usage: node scripts/serve.mjs [port=5189] [root=site]
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync, createReadStream } from "node:fs";
import { join, extname, normalize, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const rootArg = process.argv[3] || process.env.DEMURRAGE_SITE_ROOT;
const ROOT = rootArg ? resolve(rootArg) : join(WEB, "site");
const PORT = Number(process.argv[2] || process.env.PORT || 5189);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".zip": "application/zip",
  ".csv": "text/csv; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".sha256": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

function parseHeaders() {
  const p = join(ROOT, "_headers");
  if (!existsSync(p)) return [];
  const rules = [];
  for (const raw of readFileSync(p, "utf8").split(/\r?\n/)) {
    if (!raw.trim() || raw.trim().startsWith("#")) continue;
    if (!/^\s/.test(raw)) {
      const pat = raw.trim().replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
      rules.push({ re: new RegExp("^" + pat + "$"), h: [] });
      continue;
    }
    const i = raw.indexOf(":");
    rules.at(-1)?.h.push([raw.slice(0, i).trim(), raw.slice(i + 1).trim()]);
  }
  return rules;
}

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  for (const r of parseHeaders()) {
    if (r.re.test(url.pathname)) for (const [k, v] of r.h) res.setHeader(k, v);
  }
  let p = normalize(join(ROOT, decodeURIComponent(url.pathname)));
  if (!p.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end();
  }
  if (existsSync(p) && statSync(p).isDirectory()) p = join(p, "index.html");
  if (!existsSync(p) || (req.method !== "GET" && req.method !== "HEAD")) {
    res.writeHead(404, { "Content-Type": "text/html; charset=utf-8" });
    return res.end("not found");
  }
  res.writeHead(200, {
    "Content-Type": MIME[extname(p)] || "application/octet-stream",
    "Cache-Control": "no-cache",
  });
  if (req.method === "HEAD") return res.end();
  createReadStream(p).pipe(res);
}).listen(PORT, "127.0.0.1", () => console.log(`serving ${ROOT} on http://127.0.0.1:${PORT}`));
