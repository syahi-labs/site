import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

// Workers provide HTMLRewriter; Node does not. This stand-in records what the handler asked for,
// so the tests can check the wiring (when it runs, which selectors) without a Workers runtime.
// The stamping itself is tested in lib.test.js.
class FakeRewriter {
  static made = [];
  constructor() {
    this.rules = [];
    this.transformed = null;
    FakeRewriter.made.push(this);
  }
  on(selector, handlers) {
    this.rules.push({ selector, handlers });
    return this;
  }
  transform(response) {
    this.transformed = response;
    return new Response(response.body, { status: response.status, headers: { ...Object.fromEntries(response.headers), "x-rewritten": "1" } });
  }
}
globalThis.HTMLRewriter = FakeRewriter;

const html = (body = "<a href=\"x\">x</a>", type = "text/html; charset=utf-8") =>
  new Response(body, { status: 200, headers: { "content-type": type } });

function setup(response) {
  FakeRewriter.made.length = 0;
  const seen = [];
  const env = { ASSETS: { fetch: async (request) => (seen.push(request), response) } };
  return { env, seen };
}

const run = (url, response, init) => {
  const { env, seen } = setup(response);
  const request = new Request(url, init);
  return worker.fetch(request, env).then((res) => ({ res, seen, request }));
};

test("a redirect answers 301 with Location and never touches the assets", async () => {
  const { res, seen } = await run("https://signet.syahi.sh/deep/path?x=1", html());
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://syahi.sh/signet");
  assert.equal(seen.length, 0);
  assert.equal(FakeRewriter.made.length, 0);
});

test("www redirects keep path and query", async () => {
  const { res } = await run("https://www.syahi.sh/terms?a=b", html());
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://syahi.sh/terms?a=b");
});

test("services redirects to the quote page", async () => {
  const { res } = await run("https://services.syahi.sh/", html());
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://syahi.sh/services/quote");
});

test("a redirect carries no cookie", async () => {
  const { res } = await run("https://signet.syahi.sh/", html());
  assert.equal(res.headers.get("set-cookie"), null);
});

test("other hosts get the asset, the request passed through as it came", async () => {
  const page = html();
  const { res, seen, request } = await run("https://syahi.sh/signet", page);
  assert.equal(res, page);
  assert.equal(seen.length, 1);
  assert.equal(seen[0], request);
});

test("html without src is returned untouched", async () => {
  const page = html();
  const { res } = await run("https://syahi.sh/", page);
  assert.equal(res, page);
  assert.equal(FakeRewriter.made.length, 0);
});

test("html with an invalid src is returned untouched", async () => {
  for (const src of ["Oct", "a%22%3E%3Cscript%3E", "x".repeat(41), "", "a%20b"]) {
    const page = html();
    const { res } = await run("https://syahi.sh/?src=" + src, page);
    assert.equal(res, page, src);
    assert.equal(FakeRewriter.made.length, 0, src);
  }
});

test("a valid src on a non-html response is returned untouched", async () => {
  for (const type of ["text/css", "application/javascript", "image/webp", "application/xml", "text/plain", "application/json"]) {
    const asset = new Response("body", { headers: { "content-type": type } });
    const { res } = await run("https://syahi.sh/x?src=oct-interiors", asset);
    assert.equal(res, asset, type);
    assert.equal(FakeRewriter.made.length, 0, type);
  }
  const bare = new Response("body");
  bare.headers.delete("content-type");
  const { res } = await run("https://syahi.sh/x?src=oct-interiors", bare);
  assert.equal(res, bare);
});

test("a valid src on an empty html response is returned untouched", async () => {
  const empty = new Response(null, { status: 304, headers: { "content-type": "text/html" } });
  const { res } = await run("https://syahi.sh/?src=oct-interiors", empty);
  assert.equal(res, empty);
  assert.equal(FakeRewriter.made.length, 0);
});

test("html with a valid src is rewritten, links to wa.me and cal.com only", async () => {
  const page = html();
  const { res } = await run("https://syahi.sh/?src=oct-interiors", page);
  assert.equal(res.headers.get("x-rewritten"), "1");
  assert.equal(FakeRewriter.made.length, 1);
  const [rewriter] = FakeRewriter.made;
  assert.equal(rewriter.transformed, page);
  assert.deepEqual(rewriter.rules.map((r) => r.selector), ['a[href^="https://wa.me/"]', 'a[href^="https://cal.com/"]']);
});

test("the content type match is on the start, so charset and case do not matter", async () => {
  for (const type of ["text/html", "text/html; charset=utf-8", "TEXT/HTML;charset=UTF-8"]) {
    const { res } = await run("https://syahi.sh/?src=x1", html("<p>x</p>", type));
    assert.equal(res.headers.get("x-rewritten"), "1", type);
  }
});

function fakeAnchor(href) {
  return { href, getAttribute(n) { return n === "href" ? this.href : null; }, setAttribute(n, v) { if (n === "href") this.href = v; } };
}

test("the handlers stamp the link they are given with the request's campaign", async () => {
  await run("https://syahi.sh/?src=oct-interiors", html());
  const [wa, cal] = FakeRewriter.made[0].rules.map((r) => r.handlers);
  const a = fakeAnchor("https://wa.me/910000000000?text=Hi");
  wa.element(a);
  assert.equal(new URL(a.href).searchParams.get("text"), "Hi [ref: oct-interiors]");
  const b = fakeAnchor("https://cal.com/someone/30-min");
  cal.element(b);
  assert.equal(new URL(b.href).searchParams.get("metadata[src]"), "oct-interiors");
});

test("the handlers leave an anchor with no href alone", async () => {
  await run("https://syahi.sh/?src=x1", html());
  for (const { handlers } of FakeRewriter.made[0].rules) {
    const a = fakeAnchor(null);
    assert.doesNotThrow(() => handlers.element(a));
    assert.equal(a.href, null);
  }
});

test("each request reads its own campaign", async () => {
  const stamped = [];
  for (const src of ["one", "two"]) {
    await run("https://syahi.sh/?src=" + src, html());
    const a = fakeAnchor("https://wa.me/910000000000");
    FakeRewriter.made[0].rules[0].handlers.element(a);
    stamped.push(new URL(a.href).searchParams.get("text"));
  }
  assert.deepEqual(stamped, ["[ref: one]", "[ref: two]"]);
});

test("the Worker adds no cookie of its own to a stamped page", async () => {
  const { res } = await run("https://syahi.sh/?src=x1", html());
  assert.equal(res.headers.get("set-cookie"), null);
});
