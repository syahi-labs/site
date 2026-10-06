#!/usr/bin/env python3
"""sitecheck: static-site checks for Syahi's marketing sites. Standard library only.

    python3 sitecheck.py [--offline] [--json] [--banned-file PATH] REPO_DIR [REPO_DIR ...]

Each REPO_DIR is one static site; its host is the first line of its CNAME file.
Exit 1 if any FAIL, else 0 (2 on bad usage).
"""
import argparse
import datetime
import http.client
import json
import os
import posixpath
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, namedtuple
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from xml.parsers import expat

LEVELS = ("FAIL", "WARN", "INFO")
BANNED_PHRASES = ["personal AI agents", "research chat", "25-min", "Chhavi"]
SKIP_DIRS = {".git", ".claude", "node_modules"}
TEXT_SUFFIXES = (".html", ".xml", ".txt")  # CNAME has no suffix, so it is never scanned
CHECKED_ATTRS = ("alt", "title", "aria-label", "placeholder")  # plus content on <meta>
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
BOT_HOSTS = ("cal.com", "x.com", "instagram.com", "linkedin.com")
BOT_CODES = (403, 429, 999)  # 999 is LinkedIn's own bot block
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 sitecheck")
TIMEOUT, READ_LIMIT, WORKERS = 10, 64 * 1024, 8
EM_DASH = chr(0x2014)  # built from a code point so this file never contains the character
SEP = " " + chr(0xB7) + " "
PLACEHOLDER = re.compile(r"_{3,}|(?i:lorem\s+ipsum)|(?<![A-Za-z0-9])(?:TODO|TBD|FIXME)(?![A-Za-z0-9])")
ISO_LASTMOD = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?")


Finding = namedtuple("Finding", "repo level check path line message")  # line 0 means whole file


class Page(HTMLParser):
    """What the checks need from one HTML file. Line numbers come from getpos()."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts, self.attrs, self.links, self.headings = [], [], [], []
        self.noindex = self.refresh = self.description = self.og_image = self.canonical = False
        self.title, self._skip, self._in_title = "", 0, False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        line, rel = self.getpos()[0], set(a.get("rel", "").lower().split())
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in HEADINGS:
            self.headings.append((line, HEADINGS[tag]))
        elif tag == "meta":
            names, content = {a.get("name", "").lower(), a.get("property", "").lower()}, a.get("content", "").strip()
            self.noindex |= "robots" in names and "noindex" in content.lower()
            self.description |= "description" in names and bool(content)
            self.og_image |= "og:image" in names and bool(content)
            self.refresh |= a.get("http-equiv", "").lower() == "refresh"
        elif tag == "link" and "canonical" in rel:
            self.canonical |= bool(a.get("href", "").strip())
        for k in CHECKED_ATTRS + (("content",) if tag == "meta" else ()):
            if a.get(k):
                self.attrs.append((line, a[k]))
        if not (tag == "link" and rel & {"preconnect", "dns-prefetch"}):  # origin hints, not pages
            self.links += [(line, k, a[k]) for k in ("href", "src") if k in a]

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self._skip:
            self.texts.append((self.getpos()[0], data))


def build_rules(banned):
    """Rules every file gets: (check id, compiled regex, message builder)."""
    rules = [("em-dash", re.compile(EM_DASH), lambda m: "em dash (U+2014)")]
    for phrase in filter(str.strip, banned):
        rx = re.compile(r"\s+".join(map(re.escape, phrase.split())), re.I)
        rules.append(("banned-phrase", rx, lambda m, p=phrase: f"banned phrase: {p}"))
    return rules


PLACEHOLDER_RULE = ("placeholder", PLACEHOLDER, lambda m: f"placeholder text {m.group(0)!r}")


def scan(rules, text, line0):
    for check, rx, label in rules:
        for m in rx.finditer(text):
            yield check, line0 + text.count("\n", 0, m.start()), label(m)


def load_banned(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise argparse.ArgumentTypeError(f"cannot read {path}: {e}")
    return [x.strip() for x in lines if x.strip() and not x.lstrip().startswith("#")]


def read_cname(root):
    try:
        words = (root / "CNAME").read_text(encoding="utf-8", errors="replace").split()
    except OSError:
        return None
    first = words[0].lower() if words else ""
    return (urlsplit(first).hostname if "://" in first else first) or None


def resolve(root, urlpath):
    """Rule: P as a file, P + .html, P/index.html. Returns the repo-relative path or None."""
    root = Path(os.path.normpath(root.resolve()))
    p = unquote(urlpath).lstrip("/")
    cands = [p, p + ".html"] if p and not p.endswith("/") else []
    cands.append(posixpath.join(p, "index.html"))
    for c in cands:
        full = Path(os.path.normpath(root / c))
        if root in full.parents and full.is_file():
            return full.relative_to(root).as_posix()
    return None


def classify(page_rel, val, host):
    """Return ('internal', url_path), ('external', absolute_url) or (None, None)."""
    v = val.strip()
    if not v or v.startswith("#"):
        return None, None
    u = urlsplit(v)
    if u.netloc and u.scheme in ("", "http", "https"):
        if host and (u.hostname or "").lower() == host:
            return "internal", u.path or "/"
        return "external", urlunsplit((u.scheme or "https", u.netloc, u.path or "/", u.query, ""))
    if u.scheme:  # mailto, tel, javascript, data and friends
        return None, None
    return "internal", urlsplit(urljoin("/" + page_rel, v)).path


def check_links(root, rel, page, host, note_external, add):
    for line, attr, val in page.links:
        try:
            kind, target = classify(rel, val, host)
        except ValueError:
            add("FAIL", "internal-link", rel, line, f"malformed URL in {attr}: {val!r}")
            continue
        if kind == "internal" and resolve(root, target) is None:
            add("FAIL", "internal-link", rel, line, f"{attr} {val!r} does not resolve to a file")
        elif kind == "external":
            note_external(target, rel, line)


def fetch(url):
    """GET url, retrying once. Returns ('ok', None), ('http', code), ('timeout', None) or ('error', text)."""
    result = ("error", "no attempt")
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp.read(READ_LIMIT)
            return "ok", None
        except urllib.error.HTTPError as e:
            result = ("http", e.code)
        except (OSError, http.client.HTTPException, ValueError) as e:  # URLError and timeouts are OSErrors
            why = getattr(e, "reason", e)
            slow = isinstance(why, TimeoutError) or "timed out" in str(why)
            result = ("timeout", None) if slow else ("error", f"{type(e).__name__}: {why}")
    return result


def check_externals(refs):
    """Fetch each distinct URL once on a small thread pool; report it at every place it is used."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(fetch, refs))
    out = []
    for url, (status, detail) in zip(refs, results):
        host = (urlsplit(url).hostname or "").lower()
        bot = any(host == d or host.endswith("." + d) for d in BOT_HOSTS)
        if status == "ok":
            continue
        if status == "timeout":
            level, msg = "WARN", f"timed out after {TIMEOUT}s, twice"
        elif status == "http" and bot and detail in BOT_CODES:
            level, msg = "WARN", f"HTTP {detail} (this site blocks bots)"
        elif status == "http":
            level, msg = "FAIL", f"HTTP {detail}"
        else:
            level, msg = "FAIL", f"network error: {detail}"
        out += [Finding(repo, level, "external-link", rel, line, f"{url} {msg}") for repo, rel, line in refs[url]]
    return out


def check_robots(root, host, add):
    def note(level, line, msg):
        add(level, "robots", "robots.txt", line, msg)

    if not (root / "robots.txt").is_file():
        return note("FAIL", 0, "robots.txt is missing")
    agents, in_rules, found = [], False, False
    for n, raw in enumerate((root / "robots.txt").read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        key, sep, val = raw.split("#", 1)[0].partition(":")
        key, val = key.strip().lower(), val.strip()
        if not sep:
            continue
        if key == "user-agent":  # consecutive User-agent lines share one group
            agents, in_rules = ([] if in_rules else agents) + [val], False
        elif key in ("allow", "disallow"):
            in_rules = True
            if key == "disallow" and val == "/" and "*" in agents:
                note("FAIL", n, "Disallow: / under User-agent: * blocks the whole site")
        elif key == "sitemap" and urlsplit(val).path == "/sitemap.xml":
            found = True
            if host and (urlsplit(val).hostname or "").lower() != host:
                note("WARN", n, f"Sitemap host differs from CNAME host {host}")
    if not found:
        note("FAIL", 0, "no Sitemap: line with a /sitemap.xml URL")


def parse_sitemap(raw):
    """Return (root element name, entries); raises expat.ExpatError. Entry: {'loc': (text, line), ...}."""
    entries, st = [], {"root": None, "buf": "", "line": 0}
    p = expat.ParserCreate(namespace_separator=" ")

    def start(name, _attrs):
        st["root"] = st["root"] or name
        st["buf"], st["line"] = "", p.CurrentLineNumber
        if name in (f"{SITEMAP_NS} url", f"{SITEMAP_NS} sitemap"):
            entries.append({"line": p.CurrentLineNumber})

    def end(name):
        ns, _, local = name.rpartition(" ")
        if ns == SITEMAP_NS and local in ("loc", "lastmod") and entries:
            entries[-1][local] = (st["buf"].strip(), st["line"])

    p.StartElementHandler, p.EndElementHandler = start, end
    p.CharacterDataHandler = lambda d: st.update(buf=st["buf"] + d)
    p.Parse(raw, True)
    return st["root"], entries


def lastmod_problem(s, now):
    """None if s is a valid, non-future ISO 8601 date or datetime, else the reason it is not."""
    if not ISO_LASTMOD.fullmatch(s):
        return "is not ISO 8601 (YYYY-MM-DD or a full datetime)"
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return "is not a real date"
    dt = dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
    slack = datetime.timedelta(days=0 if "T" in s else 1)  # a bare date gets a day, as IST runs ahead of UTC
    return "is in the future" if dt > now + slack else None


def check_sitemap(root, host, pages, add):
    def note(line, msg, level="FAIL", path="sitemap.xml"):
        add(level, "sitemap", path, line, msg)

    if not (root / "sitemap.xml").is_file():
        return note(0, "sitemap.xml is missing")
    try:
        top, entries = parse_sitemap((root / "sitemap.xml").read_bytes())
    except expat.ExpatError as e:
        return note(e.lineno, f"not well-formed XML: {e}")
    if top not in (f"{SITEMAP_NS} urlset", f"{SITEMAP_NS} sitemapindex"):
        note(1, "root element is not <urlset> in the sitemaps.org namespace")
    now, listed = datetime.datetime.now(datetime.timezone.utc), set()
    for e in entries:
        loc, line = e.get("loc", ("", e["line"]))
        u = urlsplit(loc)
        if not loc:
            note(line, "entry has no <loc> text")
        elif u.scheme not in ("http", "https"):
            note(line, f"loc {loc!r} is not an absolute http(s) URL")
        else:
            if host and (u.hostname or "").lower() != host:
                note(line, f"loc {loc} is not on host {host}")
            target = resolve(root, u.path or "/")
            if target is None:
                note(line, f"loc {loc} does not resolve to a file")
            listed.add(target)
        problem = lastmod_problem(e["lastmod"][0], now) if "lastmod" in e else None
        if problem:
            note(e["lastmod"][1], f"lastmod {e['lastmod'][0]!r} {problem}")
    for rel, page in pages.items():
        if rel != "404.html" and not page.noindex and rel not in listed:
            note(0, "indexable page is not in sitemap.xml (list it or add noindex)", "WARN", rel)


def check_headings(rel, page, add):
    if page.refresh:
        return
    h1s = [line for line, level in page.headings if level == 1]
    if len(h1s) != 1:
        add("INFO", "headings", rel, h1s[0] if h1s else 0, f"{len(h1s)} h1 tags (expected 1)")
    for (_, prev), (line, level) in zip(page.headings, page.headings[1:]):
        if level > prev + 1:
            add("INFO", "headings", rel, line, f"heading level skips from h{prev} to h{level}")


def check_meta(rel, page, add):
    if page.noindex or page.refresh or rel == "404.html":
        return
    for present, what in ((page.title.strip(), "<title>"), (page.description, "meta description"),
                          (page.og_image, "og:image"), (page.canonical, "canonical link")):
        if not present:
            add("WARN", "meta", rel, 0, f"missing {what}")


def walk_files(root):
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            full = Path(dirpath, n)
            if n.lower().endswith(TEXT_SUFFIXES):
                yield full.relative_to(root).as_posix(), full


def check_repo(repo, rules, externals, host=None):
    root, out, pages = Path(repo), [], {}

    def add(level, check, path, line, msg):
        out.append(Finding(repo, level, check, path, line, msg))

    def note_external(url, rel, line):
        externals.setdefault(url, []).append((repo, rel, line))

    host = host.lower() if host else read_cname(root)
    if host is None:
        add("INFO", "cname", "CNAME", 0, "no usable CNAME file, so host checks are skipped")
    for rel, full in walk_files(root):
        text = full.read_text(encoding="utf-8", errors="replace")
        if rel.lower().endswith(".html"):
            page = pages[rel] = Page()
            page.feed(text)
            page.close()
            chunks, active = page.texts + page.attrs, rules + [PLACEHOLDER_RULE]
        else:
            chunks, active = [(1, text)], rules
        for line0, chunk in chunks:
            for check, line, msg in scan(active, chunk, line0):
                add("FAIL", check, rel, line, msg)
    for rel, page in pages.items():
        check_links(root, rel, page, host, note_external, add)
        check_headings(rel, page, add)
        check_meta(rel, page, add)
    check_robots(root, host, add)
    check_sitemap(root, host, pages, add)
    return list(dict.fromkeys(out))  # one finding per distinct (check, line, message)


def run(repos, banned=None, offline=False, host=None):
    """Check every repo and return sorted findings. The network is touched only when not offline.

    `host`, when given, is the host of every repo and replaces its CNAME file: for a build's output
    directory, which holds no CNAME."""
    rules = build_rules(BANNED_PHRASES if banned is None else banned)
    repos = list(dict.fromkeys(str(r) for r in repos))
    findings, externals = [], {}
    for repo in repos:
        findings += check_repo(repo, rules, externals, host)
    if externals and not offline:
        findings += check_externals(externals)
    order = {r: i for i, r in enumerate(repos)}
    findings.sort(key=lambda f: (order[f.repo], LEVELS.index(f.level), f.path, f.line, f.check))
    return findings


def render(findings, repos):
    out = []
    for repo in repos:
        mine = [f for f in findings if f.repo == repo]
        out.append(f"== {repo} ==" + ("" if mine else " clean"))
        for level in LEVELS:
            group = [f for f in mine if f.level == level]
            out += [f"{level} ({len(group)})"] if group else []
            out += [f"  [{f.check}] {f.path}{':%d' % f.line if f.line else ''}  {f.message}" for f in group]
        out.append("")
    counts = Counter(f.level for f in findings)
    return "\n".join(out + [SEP.join(f"{level} {counts[level]}" for level in LEVELS)])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Static-site checks for Syahi marketing sites.")
    ap.add_argument("repos", nargs="+", metavar="REPO_DIR")
    ap.add_argument("--offline", action="store_true", help="skip external link checks")
    ap.add_argument("--json", action="store_true", help="print findings as a JSON list")
    ap.add_argument("--banned-file", type=load_banned, metavar="PATH",
                    help="one phrase per line; lines starting with # are comments")
    args = ap.parse_args(argv)
    for d in args.repos:
        if not os.path.isdir(d):
            ap.error(f"not a directory: {d}")
    findings = run(args.repos, args.banned_file, args.offline)
    if args.json:
        print(json.dumps([f._asdict() for f in findings], indent=2))
    else:
        print(render(findings, list(dict.fromkeys(args.repos))))
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
