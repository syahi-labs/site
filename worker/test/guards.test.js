import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

// The privacy ruling (D20): no cookie, no logged or stored IP or user agent, no injected script,
// and a campaign name is the only thing the Worker ever reads from a visitor. These guards read the
// Worker's own source and its config, so a later edit that breaks the ruling fails here.

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const read = (p) => readFileSync(here(p), "utf8");
const code = (p) => read(p).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/ .*$/gm, "");
const SOURCES = readdirSync(here("../src")).filter((n) => n.endsWith(".js")).map((n) => "../src/" + n);

test("the source files are the two we expect", () => {
  assert.deepEqual(SOURCES, ["../src/index.js", "../src/lib.js"]);
});

const FORBIDDEN = [
  [/cookie/i, "a cookie"],
  [/console\b/, "logging"],
  [/cf-connecting-ip|x-forwarded-for|x-real-ip|true-client-ip|\bremoteAddr/i, "an IP address"],
  [/user-agent|userAgent/i, "a user agent"],
  [/request\.cf\b|\.cf\b/, "Cloudflare request metadata"],
  [/<script|createElement|innerHTML|\.append\(|\.prepend\(|\.before\(|\.after\(|setInnerContent|onEndTag|onDocument/, "injected markup"],
  [/\bKV\b|\.put\(|\bD1\b|waitUntil|caches\b|\bsendBeacon|\bXMLHttpRequest/, "storage or a side channel"],
  [/analytics|telemetry|\btrack(?:ing)?\b/i, "analytics"],
  [/Math\.random|crypto\.|Date\.now|new Date/, "a per-visitor token or clock"],
];

for (const file of SOURCES) {
  test(`${file} never touches what the privacy ruling forbids`, () => {
    const src = code(file);
    for (const [pattern, what] of FORBIDDEN) assert.doesNotMatch(src, pattern, `${file} mentions ${what}`);
  });
}

test("the only network calls are the asset binding and the passthrough for other hosts", () => {
  const calls = SOURCES.flatMap((f) => code(f).replace("async fetch(", "").match(/\bfetch\s*\(/g) || []);  // minus the handler's own definition
  assert.equal(calls.length, 2);
  assert.match(code("../src/index.js"), /env\.ASSETS\.fetch\(request\)/);
  assert.match(code("../src/index.js"), /if \(!isSiteHost\(url\)\) return fetch\(request\);/);
  for (const f of SOURCES) assert.doesNotMatch(code(f), /https?:\/\/(?!syahi\.sh|wa\.me|cal\.com)/);
});

test("the Worker reads the request URL and the asset response, nothing more", () => {
  const reads = [...code("../src/index.js").matchAll(/request\.([A-Za-z]+)/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(reads)].sort(), ["url"]);
});

test("the source holds no em dash", () => {
  const dash = String.fromCharCode(0x2014);
  for (const f of [...SOURCES, "../test/lib.test.js", "../test/index.test.js", "../test/guards.test.js", "../wrangler.toml", "../package.json", "../README.md"]) {
    assert.ok(!read(f).includes(dash), f);
  }
});

// ---- wrangler.toml ----

const toml = read("../wrangler.toml");
const lines = toml.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));

test("wrangler.toml names the Worker and its assets", () => {
  for (const line of [
    'name = "syahi-site"',
    'directory = "../dist/syahi.sh"',
    'binding = "ASSETS"',
    'html_handling = "auto-trailing-slash"',
    'not_found_handling = "404-page"',
    "run_worker_first = true",
  ]) {
    assert.ok(lines.includes(line), `missing: ${line}`);
  }
  assert.ok(lines.includes("[assets]"));
});

test("wrangler.toml has a compatibility date and the entry point", () => {
  assert.ok(lines.some((l) => /^compatibility_date = "\d{4}-\d{2}-\d{2}"$/.test(l)));
  assert.ok(lines.includes('main = "src/index.js"'));
});

test("wrangler.toml has no routes, custom domains or bindings (Part C adds the routes)", () => {
  const keys = lines.map((l) => l.replace(/^\[+|\]+$/g, "").split("=")[0].trim());
  for (const banned of ["route", "routes", "pattern", "custom_domain", "zone_name", "zone_id", "kv_namespaces", "d1_databases", "r2_buckets", "analytics_engine_datasets", "queues", "services", "durable_objects", "vars", "logpush", "tail_consumers", "triggers"]) {
    assert.ok(!keys.includes(banned), `wrangler.toml has ${banned}`);
  }
});

test("wrangler.toml turns the public workers.dev address off and preview URLs off", () => {
  assert.ok(lines.includes("workers_dev = false"), "missing: workers_dev = false");
  assert.ok(lines.includes("preview_urls = false"), "missing: preview_urls = false");
});

test("wrangler.toml keeps request logging off", () => {
  const section = toml.match(/\[observability\][^\[]*/);
  if (section) assert.match(section[0], /enabled\s*=\s*false/);
  assert.doesNotMatch(toml, /enabled\s*=\s*true/);
  assert.doesNotMatch(toml, /\[observability\.logs\]|head_sampling_rate|invocation_logs/);
});
