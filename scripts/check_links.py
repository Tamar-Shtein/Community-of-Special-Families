"""Weekly automation: check that every source link in the guide still works.

    trigger  -> once a week (GitHub Actions schedule), or "Run workflow"
    filter   -> only links that are actually broken (404, 410, site not found)
    action   -> save the result to data/links-status.json (shown on the page),
                and the workflow opens a GitHub Issue listing the broken links

A link that answers 403/429/5xx or times out is "could not check", not
"broken": some sites block automated visitors, and that is not a dead page.

Run:  python scripts/check_links.py
"""
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

PAGE = "index.html"
OUT = "data/links-status.json"
BROKEN_CODES = {404, 410}
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 community-guide-link-check")


class Links(HTMLParser):
    """Collect every <a href="http..."> with its visible text."""
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("http"):
                self._href, self._text = href, []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.links.append({"url": self._href, "text": text})
            self._href = None


def check(url):
    """Return (state, detail): state is ok / broken / unknown."""
    # Hebrew page names must be percent-encoded before sending
    parts = urllib.parse.urlsplit(url)
    safe = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe="/%()_-.,")))
    for method in ("HEAD", "GET"):          # some servers refuse HEAD; retry with GET
        req = urllib.request.Request(safe, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return "ok", r.status
        except urllib.error.HTTPError as e:
            if e.code in BROKEN_CODES:
                return "broken", e.code
            if method == "HEAD":
                continue
            return "unknown", e.code
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.gaierror):
                return "broken", "site not found"
            if method == "HEAD":
                continue
            return "unknown", str(e.reason)
        except (TimeoutError, socket.timeout):
            if method == "HEAD":
                continue
            return "unknown", "timeout"
    return "unknown", "no answer"


parser = Links()
with open(PAGE, encoding="utf-8") as f:
    parser.feed(f.read())

# The same link can appear more than once on the page; check each URL once
seen, links = set(), []
for l in parser.links:
    if l["url"] not in seen:
        seen.add(l["url"])
        links.append(l)

results = []
for l in links:
    state, detail = check(l["url"])
    results.append({**l, "state": state, "detail": detail})
    print(f"  {state:8} {detail!s:16} {l['text']}")

counts = {s: sum(r["state"] == s for r in results) for s in ("ok", "broken", "unknown")}
out = {
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "total": len(results),
    **counts,
    "links": results,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# Count in, count out
assert counts["ok"] + counts["broken"] + counts["unknown"] == len(results)
print(f"Links: {len(results)} | ok: {counts['ok']} | broken: {counts['broken']} | could not check: {counts['unknown']}")
sys.exit(0)
