# worker

The Cloudflare Worker in front of syahi.sh. It does two things.

1. Real 301 redirects. `signet.syahi.sh` goes to `/signet`, `services.syahi.sh` goes to `/services/quote`, and `www.syahi.sh` goes to the bare domain with path and query kept. Every other host is untouched.
2. Campaign stamping. On an HTML page requested with `?src=<campaign>`, links to `wa.me` get ` [ref: <campaign>]` added to their message text and links to `cal.com` get `metadata[src]=<campaign>`. A campaign is `^[a-z0-9-]{1,40}$` or it is ignored. It names a campaign, never a person.

What it never does. It sets no cookie. It logs and stores no IP address and no user agent. It adds no script. It reads the request URL and nothing else from the visitor. `test/guards.test.js` fails if the source or `wrangler.toml` drifts from that.

Run the tests (Node 22 or later, no npm packages, no network):

    cd worker && node --test

It is written and unit-tested here, not deployed. Routes, custom domains and the deploy are Part C, done with her Cloudflare token.
