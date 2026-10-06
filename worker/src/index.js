// Redirects, then the static site, then (only with a valid ?src=) a campaign stamp on the booking links.
// The logic lives in lib.js. This file reads the request URL and the asset response, nothing else.
import { redirectFor, sanitizeSrc, stampWhatsApp, stampCal } from "./lib.js";

const isHtml = (response) => (response.headers.get("content-type") || "").toLowerCase().startsWith("text/html");

const stamper = (stamp) => ({
  element(anchor) {
    const href = anchor.getAttribute("href");
    if (href) anchor.setAttribute("href", stamp(href));
  },
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const target = redirectFor(url);
    if (target) return Response.redirect(target, 301);

    const response = await env.ASSETS.fetch(request);
    const src = sanitizeSrc(url.searchParams.get("src"));
    if (src === null || response.body === null || !isHtml(response)) return response;

    return new HTMLRewriter()
      .on('a[href^="https://wa.me/"]', stamper((href) => stampWhatsApp(href, src)))
      .on('a[href^="https://cal.com/"]', stamper((href) => stampCal(href, src)))
      .transform(response);
  },
};
