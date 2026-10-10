import { test } from "node:test";
import assert from "node:assert/strict";
import { isSiteHost, redirectFor, cleanUrlFor, sanitizeSrc, stampWhatsApp, stampCal } from "../src/lib.js";

// ---- the brief's own tests, verbatim ----

test("subdomain redirects", () => {
  assert.equal(redirectFor(new URL("https://signet.syahi.sh/anything?x=1")), "https://syahi.sh/signet?x=1");
  assert.equal(redirectFor(new URL("https://services.syahi.sh/")), "https://syahi.sh/services/quote");
  assert.equal(redirectFor(new URL("https://www.syahi.sh/terms?a=b")), "https://syahi.sh/terms?a=b");
  assert.equal(redirectFor(new URL("https://syahi.sh/signet")), null);
});

test("src is sanitised", () => {
  assert.equal(sanitizeSrc("oct-interiors"), "oct-interiors");
  assert.equal(sanitizeSrc("Oct"), null);
  assert.equal(sanitizeSrc("a\"><script>"), null);
  assert.equal(sanitizeSrc("x".repeat(41)), null);
  assert.equal(sanitizeSrc(null), null);
});

test("whatsapp stamp keeps existing text", () => {
  const out = new URL(stampWhatsApp("https://wa.me/910000000000?text=Hi%20there", "oct-interiors"));
  assert.equal(out.searchParams.get("text"), "Hi there [ref: oct-interiors]");
  const bare = new URL(stampWhatsApp("https://wa.me/910000000000", "x1"));
  assert.equal(bare.searchParams.get("text"), "[ref: x1]");
});

test("cal stamp adds metadata", () => {
  const out = new URL(stampCal("https://cal.com/someone/30-min?overlayCalendar=true", "x1"));
  assert.equal(out.searchParams.get("metadata[src]"), "x1");
  assert.equal(out.searchParams.get("overlayCalendar"), "true");
});

// ---- redirectFor ----

test("signet and services collapse every path and keep the query", () => {
  for (const [path, query] of [["/", ""], ["/a", ""], ["/a/b/c", ""], ["/a", "?x=1"], ["/", "?utm=1"], ["/a/b", "?x=1&y=2"]]) {
    assert.equal(redirectFor(new URL("https://signet.syahi.sh" + path + query)), "https://syahi.sh/signet" + query, path + query);
    assert.equal(redirectFor(new URL("https://services.syahi.sh" + path + query)), "https://syahi.sh/services/quote" + query, path + query);
  }
});

test("a campaign stamp survives the signet and services redirects", () => {
  assert.equal(redirectFor(new URL("https://signet.syahi.sh/?src=oct-interiors")), "https://syahi.sh/signet?src=oct-interiors");
  assert.equal(redirectFor(new URL("https://services.syahi.sh/x?src=oct-interiors")), "https://syahi.sh/services/quote?src=oct-interiors");
});

test("only syahi.sh itself is a site host", () => {
  assert.equal(isSiteHost(new URL("https://syahi.sh/x")), true);
  assert.equal(isSiteHost(new URL("https://SYAHI.sh./x")), true);
  for (const h of ["approve.syahi.sh", "listen.katha.syahi.sh", "media.syahi.sh", "hook.syahi.sh", "katha.syahi.sh", "syahi.sh.example"]) {
    assert.equal(isSiteHost(new URL(`https://${h}/`)), false, h);
  }
});

test("www keeps path and query, and the root stays the root", () => {
  assert.equal(redirectFor(new URL("https://www.syahi.sh/")), "https://syahi.sh/");
  assert.equal(redirectFor(new URL("https://www.syahi.sh")), "https://syahi.sh/");
  assert.equal(redirectFor(new URL("https://www.syahi.sh/services/quote")), "https://syahi.sh/services/quote");
  assert.equal(redirectFor(new URL("https://www.syahi.sh/a/b?x=1&y=%20z")), "https://syahi.sh/a/b?x=1&y=%20z");
  assert.equal(redirectFor(new URL("https://www.syahi.sh/?src=oct-interiors")), "https://syahi.sh/?src=oct-interiors");
});

test("a www path can never point the redirect off syahi.sh", () => {
  for (const path of ["//evil.example/x", "/\\evil.example", "/@evil.example", "///evil.example"]) {
    const out = redirectFor(new URL("https://www.syahi.sh" + path));
    assert.ok(out.startsWith("https://syahi.sh/"), out);
    assert.equal(new URL(out).hostname, "syahi.sh", out);
  }
});

test("host matching ignores case and a trailing dot", () => {
  assert.equal(redirectFor(new URL("https://SIGNET.Syahi.SH/x")), "https://syahi.sh/signet");
  assert.equal(redirectFor(new URL("https://signet.syahi.sh./x")), "https://syahi.sh/signet");
  assert.equal(redirectFor(new URL("https://www.syahi.sh./a?b=c")), "https://syahi.sh/a?b=c");
});

test("the port does not change which host it is", () => {
  assert.equal(redirectFor(new URL("https://signet.syahi.sh:8443/x")), "https://syahi.sh/signet");
});

test("every other host is left alone", () => {
  const others = [
    "https://syahi.sh/",
    "https://syahi.sh/signet",
    "https://approve.syahi.sh/",
    "https://approve.syahi.sh/inbox?x=1",
    "https://listen.katha.syahi.sh/",
    "https://katha.syahi.sh/",
    "https://katha.syahi.sh/feed.xml",
    "https://media.katha.syahi.sh/ep1.mp3",
    "https://hook.syahi.sh/",
    "https://hook.syahi.sh/inbound",
    "https://www.katha.syahi.sh/",
    "https://signet.katha.syahi.sh/",
    "https://old.signet.syahi.sh/",
    "https://old.www.syahi.sh/",
    "https://mail.syahi.sh/",
    "https://signet.syahi.sh.example/",
    "https://www.syahi.sh.example/",
    "https://signet-syahi.sh/",
    "https://notsignet.syahi.sh/",
    "https://wwww.syahi.sh/",
    "https://example.com/",
    "https://localhost/",
  ];
  for (const u of others) assert.equal(redirectFor(new URL(u)), null, u);
});

// ---- sanitizeSrc ----

test("src accepts exactly lowercase letters, digits and hyphens, 1 to 40 long", () => {
  for (const ok of ["a", "9", "-", "oct-interiors", "x1", "2026-10-oct", "a".repeat(40), "0-9-a-z"]) {
    assert.equal(sanitizeSrc(ok), ok, ok);
  }
});

test("src rejects everything else", () => {
  const bad = [
    "", " ", "Oct", "OCT", "oct_interiors", "oct interiors", "oct.interiors", "oct/x", "a+b", "a%20b", "a&b=c",
    "a=b", "a\"b", "a'b", "a<b", "a>b", "<script>", "é", "स्याही", "a\nb", "a\n", "\na", "a\r", "a\t",
    "a b", "x".repeat(41), "x".repeat(400), "a\u0000", "../x", "a;b", "a[ref]",
  ];
  for (const b of bad) assert.equal(sanitizeSrc(b), null, JSON.stringify(b));
});

test("src is not a string means no src", () => {
  for (const v of [null, undefined, 0, 1, true, {}, [], ["oct"], { toString: () => "oct" }]) {
    assert.equal(sanitizeSrc(v), null, String(typeof v));
  }
});

// ---- stampWhatsApp ----

const WA = "https://wa.me/910000000000";

test("whatsapp: appends to the text with a single space", () => {
  assert.equal(
    stampWhatsApp(WA + "?text=Hi%20there", "oct-interiors"),
    WA + "?text=Hi%20there%20%5Bref%3A%20oct-interiors%5D",
  );
});

test("whatsapp: adds text when it is absent or empty", () => {
  assert.equal(stampWhatsApp(WA, "x1"), WA + "?text=%5Bref%3A%20x1%5D");
  assert.equal(stampWhatsApp(WA + "?text=", "x1"), WA + "?text=%5Bref%3A%20x1%5D");
  assert.equal(stampWhatsApp(WA + "?lang=en", "x1"), WA + "?lang=en&text=%5Bref%3A%20x1%5D");
});

test("whatsapp: spaces go out as %20, never as +", () => {
  const out = stampWhatsApp(WA + "?text=Hi+there", "x1");
  assert.ok(!out.includes("+"), out);
  assert.equal(new URL(out).searchParams.get("text"), "Hi there [ref: x1]");
});

test("whatsapp: other parameters, their order and their bytes survive", () => {
  const out = stampWhatsApp(WA + "?a=1%2C2&text=Hello&z=%20q", "x1");
  assert.equal(out, WA + "?a=1%2C2&text=Hello%20%5Bref%3A%20x1%5D&z=%20q");
});

test("whatsapp: non-ASCII text round-trips", () => {
  const text = "नमस्ते café";
  const out = new URL(stampWhatsApp(WA + "?text=" + encodeURIComponent(text), "x1"));
  assert.equal(out.searchParams.get("text"), text + " [ref: x1]");
});

test("whatsapp: the fragment survives", () => {
  assert.equal(stampWhatsApp(WA + "#frag", "x1"), WA + "?text=%5Bref%3A%20x1%5D#frag");
});

test("whatsapp: stamping twice does not stamp twice", () => {
  for (const start of [WA, WA + "?text=Hi%20there", WA + "?text=", WA + "?a=1&text=Hi&b=2"]) {
    const once = stampWhatsApp(start, "oct-interiors");
    assert.equal(stampWhatsApp(once, "oct-interiors"), once, start);
    const refs = new URL(once).searchParams.get("text").match(/\[ref: /g);
    assert.equal(refs.length, 1, start);
  }
});

test("whatsapp: a second, different campaign replaces the first tag", () => {
  const first = stampWhatsApp(WA + "?text=Hi", "one");
  const second = stampWhatsApp(first, "two");
  assert.equal(new URL(second).searchParams.get("text"), "Hi [ref: two]");
  assert.equal(new URL(stampWhatsApp(stampWhatsApp(WA, "one"), "two")).searchParams.get("text"), "[ref: two]");
});

test("whatsapp: duplicate text parameters collapse to one stamped text", () => {
  const out = new URL(stampWhatsApp(WA + "?text=a&text=b", "x1"));
  assert.deepEqual(out.searchParams.getAll("text"), ["a [ref: x1]"]);
});

test("whatsapp: links it does not recognise come back unchanged", () => {
  const unchanged = [
    "http://wa.me/910000000000",
    "https://wa.me.evil.example/910000000000",
    "https://evil.example/wa.me/910000000000",
    "https://wa.me@evil.example/910000000000",
    "https://api.whatsapp.com/send?phone=910000000000",
    "https://wa.me:8443/910000000000",
    "https://cal.com/someone/30-min",
    "/910000000000",
    "wa.me/910000000000",
    "//wa.me/910000000000",
    "wa.me",
    "mailto:hello@syahi.example",
    "tel:+910000000000",
    "javascript:alert(1)",
    "https://",
    "https://[",
    "http://[::1",
    "",
    "   ",
    "#top",
    "?text=x",
  ];
  for (const href of unchanged) {
    assert.equal(stampWhatsApp(href, "x1"), href, JSON.stringify(href));
  }
});

test("whatsapp: never throws on odd input", () => {
  for (const href of ["https://wa.me/1?text=%", "https://wa.me/1?text=%E0%A4%A", "https://wa.me/1?text=\ud800", "https://wa.me/1?%=%&&=&="]) {
    assert.doesNotThrow(() => stampWhatsApp(href, "x1"), href);
  }
});

test("whatsapp: a src that fails the rule is never written", () => {
  for (const bad of ["Oct", "a b", "x".repeat(41), "", null, undefined, "a\"><script>"]) {
    assert.equal(stampWhatsApp(WA + "?text=Hi", bad), WA + "?text=Hi", String(bad));
  }
});

// ---- stampCal ----

const CAL = "https://cal.com/someone/30-min";

test("cal: sets metadata[src] and keeps everything else", () => {
  const out = new URL(stampCal(CAL + "?overlayCalendar=true&name=A%20B", "oct-interiors"));
  assert.equal(out.searchParams.get("metadata[src]"), "oct-interiors");
  assert.equal(out.searchParams.get("overlayCalendar"), "true");
  assert.equal(out.searchParams.get("name"), "A B");
  assert.equal(out.pathname, "/someone/30-min");
});

test("cal: a bare link gets a query, and the other bytes survive", () => {
  assert.equal(stampCal(CAL, "x1"), CAL + "?metadata%5Bsrc%5D=x1");
  assert.equal(
    stampCal(CAL + "?name=A%20B&theme=dark", "x1"),
    CAL + "?name=A%20B&theme=dark&metadata%5Bsrc%5D=x1",
  );
});

test("cal: the fragment survives", () => {
  assert.equal(stampCal(CAL + "#slots", "x1"), CAL + "?metadata%5Bsrc%5D=x1#slots");
});

test("cal: an existing metadata[src] is replaced, in place, once", () => {
  const out = stampCal(CAL + "?a=1&metadata%5Bsrc%5D=old&b=2", "new-one");
  assert.equal(out, CAL + "?a=1&metadata%5Bsrc%5D=new-one&b=2");
  const literal = new URL(stampCal(CAL + "?metadata[src]=old&metadata[src]=again", "new-one"));
  assert.deepEqual(literal.searchParams.getAll("metadata[src]"), ["new-one"]);
});

test("cal: other metadata keys are left alone", () => {
  const out = new URL(stampCal(CAL + "?metadata[page]=home", "x1"));
  assert.equal(out.searchParams.get("metadata[page]"), "home");
  assert.equal(out.searchParams.get("metadata[src]"), "x1");
});

test("cal: stamping twice does not stamp twice", () => {
  for (const start of [CAL, CAL + "?overlayCalendar=true", CAL + "?metadata[src]=old"]) {
    const once = stampCal(start, "oct-interiors");
    assert.equal(stampCal(once, "oct-interiors"), once, start);
    assert.deepEqual(new URL(once).searchParams.getAll("metadata[src]"), ["oct-interiors"], start);
  }
});

test("cal: links it does not recognise come back unchanged", () => {
  const unchanged = [
    "http://cal.com/someone/30-min",
    "https://cal.com.evil.example/someone/30-min",
    "https://evil.example/cal.com/someone/30-min",
    "https://cal.com@evil.example/someone",
    "https://app.cal.com/someone/30-min",
    "https://www.cal.com/someone/30-min",
    "https://cal.com:8443/someone/30-min",
    "https://wa.me/910000000000",
    "/someone/30-min",
    "cal.com/someone/30-min",
    "//cal.com/someone/30-min",
    "mailto:hello@syahi.example",
    "javascript:alert(1)",
    "https://",
    "https://[",
    "",
    "   ",
    "#book",
    "?x=1",
  ];
  for (const href of unchanged) {
    assert.equal(stampCal(href, "x1"), href, JSON.stringify(href));
  }
});

test("cal: never throws on odd input", () => {
  for (const href of ["https://cal.com/x?%", "https://cal.com/x?metadata[src]=%E0%A4%A", "https://cal.com/x?a=\ud800", "https://cal.com/x?%=%&&=&="]) {
    assert.doesNotThrow(() => stampCal(href, "x1"), href);
  }
});

test("cal: a src that fails the rule is never written", () => {
  for (const bad of ["Oct", "a b", "x".repeat(41), "", null, undefined, "a\"><script>"]) {
    assert.equal(stampCal(CAL + "?a=1", bad), CAL + "?a=1", String(bad));
  }
});

test("the stamp functions agree on what a campaign is", () => {
  const src = "a".repeat(40);
  assert.equal(sanitizeSrc(src), src);
  assert.equal(new URL(stampWhatsApp(WA, src)).searchParams.get("text"), `[ref: ${src}]`);
  assert.equal(new URL(stampCal(CAL, src)).searchParams.get("metadata[src]"), src);
});

// ---- cleanUrlFor: one clean URL per page, by 301 ----

test("a .html name, a trailing slash and /index.html redirect to the clean URL", () => {
  const want = {
    "/signet.html": "/signet",
    "/signet/": "/signet",
    "/signet//": "/signet",
    "/services/quote.html": "/services/quote",
    "/services/quote/": "/services/quote",
    "/katha/": "/katha",
    "/index.html": "/",
    "/services/index.html": "/services",
    "/.html": "/",
  };
  for (const [path, clean] of Object.entries(want)) {
    assert.equal(cleanUrlFor(new URL("https://syahi.sh" + path)), "https://syahi.sh" + clean, path);
  }
});

test("clean URLs and the root are left alone", () => {
  for (const path of ["/", "/signet", "/services/quote", "/assets/base.6f962a67fe.css", "/robots.txt", "/sitemap.xml", "/nope"]) {
    assert.equal(cleanUrlFor(new URL("https://syahi.sh" + path)), null, path);
  }
});

test("the query string is kept byte for byte", () => {
  assert.equal(cleanUrlFor(new URL("https://syahi.sh/signet.html?src=oct-x&a=b%20c")), "https://syahi.sh/signet?src=oct-x&a=b%20c");
  assert.equal(cleanUrlFor(new URL("https://syahi.sh/signet/?src=x")), "https://syahi.sh/signet?src=x");
  assert.equal(cleanUrlFor(new URL("https://syahi.sh/index.html?src=x")), "https://syahi.sh/?src=x");
});

test("the target is always syahi.sh, whatever the path says (no open redirect)", () => {
  for (const path of ["//evil.example/", "//evil.example.html", "/\\evil.example/", "///evil.example/x/", "/%2F%2Fevil.example/", "/@evil.example/", "/https://evil.example/"]) {
    const out = cleanUrlFor(new URL("https://syahi.sh" + path));
    if (out === null) continue;
    assert.equal(new URL(out).host, "syahi.sh", path);
    assert.equal(new URL(out).protocol, "https:", path);
    assert.ok(out.startsWith("https://syahi.sh/"), out);
    assert.ok(!out.startsWith("https://syahi.sh//"), out);
  }
});

test("a redirect target is itself clean, so there is never a second hop", () => {
  for (const path of ["/a.html", "/a/", "/a/index.html", "/index.html", "//a.html", "/a.html/", "/a/b.html//"]) {
    const out = cleanUrlFor(new URL("https://syahi.sh" + path));
    if (out !== null) assert.equal(cleanUrlFor(new URL(out)), null, path + " -> " + out);
  }
});

test("only the site host gets clean-URL redirects", () => {
  for (const host of ["approve.syahi.sh", "katha.syahi.sh", "listen.katha.syahi.sh", "media.syahi.sh", "hook.syahi.sh", "unknown.example"]) {
    assert.equal(cleanUrlFor(new URL(`https://${host}/signet.html`)), null, host);
  }
  assert.equal(cleanUrlFor(new URL("https://SYAHI.SH/signet.html")), "https://syahi.sh/signet");
});
