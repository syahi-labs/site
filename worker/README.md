# worker

The Cloudflare Worker in front of syahi.sh. It does three things.

1. Real 301 redirects. `signet.syahi.sh` goes to `/signet`, `services.syahi.sh` goes to `/services/quote`, and `www.syahi.sh` goes to the bare domain with path and query kept. The query string is kept on all three, so a `?src=` stamp survives. The site is served only for `syahi.sh`: any other host (approve., listen.katha., media., hook.) is passed straight through to its own origin, so a broad route can never shadow it.
2. One clean URL per page. On `syahi.sh`, `/x.html`, `/x/` and `/index.html` get a real 301 to `/x` (or `/`), query kept, always to the fixed host `syahi.sh`. The assets layer (`html_handling`) would answer 307 for these, and the other `html_handling` values either do the same or stop serving `/x`, so the Worker answers first. `/` itself is never redirected.
3. Campaign stamping. On an HTML page requested with `?src=<campaign>`, links to `wa.me` get ` [ref: <campaign>]` added to their message text and links to `cal.com` get `metadata[src]=<campaign>`. A campaign is `^[a-z0-9-]{1,40}$` or it is ignored. It names a campaign, never a person.

What it never does. It sets no cookie. It logs and stores no IP address and no user agent. It adds no script. It reads the request URL and nothing else from the visitor. `test/guards.test.js` fails if the source or `wrangler.toml` drifts from that.

Run the tests (Node 22 or later, no npm packages, no network):

    cd worker && node --test

It is written and unit-tested here, not deployed. Routes, custom domains and the deploy are Part C, done with her Cloudflare token.
