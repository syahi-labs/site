// The Worker's logic, as pure functions. Nothing here reads the network, the clock or a visitor.
// The only thing taken from a visitor anywhere in the Worker is a campaign name (see sanitizeSrc).

const CAMPAIGN = /^[a-z0-9-]{1,40}$/;

/** Whether the Worker serves the site for this host. Every other host (approve., listen.katha., media., hook.) is not ours to answer. */
export function isSiteHost(url) {
  return url.hostname.toLowerCase().replace(/\.$/, "") === "syahi.sh";
}

/** Where a request should be sent with a 301, or null when the Worker should serve it. */
export function redirectFor(url) {
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (host === "signet.syahi.sh") return `https://syahi.sh/signet${url.search}`;
  if (host === "services.syahi.sh") return `https://syahi.sh/services/quote${url.search}`;
  if (host === "www.syahi.sh") return `https://syahi.sh${url.pathname}${url.search}`;
  return null;
}

// One clean path: no repeated slash, no trailing slash, no /index.html, no .html. The root stays "/".
function cleanPath(pathname) {
  let path = pathname;
  for (;;) {
    let next = path.replace(/\/{2,}/g, "/").replace(/(.)\/+$/, "$1");
    if (next.endsWith("/index.html")) next = next.slice(0, -"index.html".length);
    else if (next.endsWith(".html")) next = next.slice(0, -".html".length);
    next = next.replace(/(.)\/+$/, "$1") || "/";
    if (next === path) return path;
    path = next;
  }
}

/**
 * Where a site-host request for a non-clean URL (/x.html, /x/, /index.html) should go with a 301, or null.
 * The target is built from the fixed host plus a path with no leading double slash, so it can only ever
 * land on syahi.sh. The query string is carried over untouched. The root "/" is never redirected.
 */
export function cleanUrlFor(url) {
  if (!isSiteHost(url)) return null;
  const clean = cleanPath(url.pathname);
  if (clean === url.pathname) return null;
  return `https://syahi.sh${clean}${url.search}`;
}

/** The campaign name when it is safe to write into a page, else null. Never anything about a person. */
export function sanitizeSrc(raw) {
  return typeof raw === "string" && CAMPAIGN.test(raw) ? raw : null;
}

// Set one query parameter and leave every other byte of the query as the page's author wrote it.
// The new value is percent-encoded (a space is %20, never +), and any repeats of the name collapse into it.
function setParam(url, name, valueFor) {
  const segments = url.search.slice(1).split("&").filter(Boolean);
  const keyOf = (segment) => new URLSearchParams(segment).keys().next().value;
  const first = segments.findIndex((segment) => keyOf(segment) === name);
  const old = first === -1 ? null : new URLSearchParams(segments[first]).get(name);
  const written = `${encodeURIComponent(name)}=${encodeURIComponent(valueFor(old))}`;
  const kept = [];
  segments.forEach((segment, i) => {
    if (i === first) kept.push(written);
    else if (keyOf(segment) !== name) kept.push(segment);
  });
  if (first === -1) kept.push(written);
  url.search = kept.join("&");
}

// Stamp a link on one exact origin. Anything else (another host, a relative or malformed href, a
// campaign that fails the rule) comes back exactly as it went in.
function stamp(href, src, origin, name, valueFor) {
  if (sanitizeSrc(src) === null) return href;
  let url;
  try {
    url = new URL(href);
  } catch {
    return href;
  }
  if (url.origin !== origin) return href;
  setParam(url, name, valueFor);
  return url.href;
}

const REF_TAG = /\s*\[ref: [a-z0-9-]{1,40}\]$/;

/** wa.me links: the campaign rides in the message text as " [ref: <src>]". A second stamp replaces the first. */
export function stampWhatsApp(href, src) {
  return stamp(href, src, "https://wa.me", "text", (text) => {
    const base = (text ?? "").replace(REF_TAG, "").trimEnd();
    return base ? `${base} [ref: ${src}]` : `[ref: ${src}]`;
  });
}

/** cal.com links: the campaign rides in the booking's metadata[src]. A second stamp replaces the first. */
export function stampCal(href, src) {
  return stamp(href, src, "https://cal.com", "metadata[src]", () => src);
}
