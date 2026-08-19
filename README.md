# syahi.sh
Company site for Syahi (स्याही). Static, GitHub Pages. index.html plus the four live plates in art/ (cube, gramophone, inkpot, loom — webp). If a plate is added to or dropped from index.html, update the .gitignore allowlist to match or it 404s.
Deploy: push to main → Settings → Pages → Deploy from branch (main, root). Custom domain: syahi.sh (CNAME file included).
Everything else in art/ (spare plates: book, moth, ring, seal) and all of brand/ (mark sources, BRAND.md, letterhead, stamps) is local-only and gitignored — this repo is public. book.webp was the Visual Reads plate, parked 2026-07-26; the spares wait for future ventures.
index-v1-classic.html is the v1 backup, not linked from anywhere.
DNS at Porkbun: ALIAS syahi.sh → <org-or-user>.github.io · CNAME www → <org-or-user>.github.io
