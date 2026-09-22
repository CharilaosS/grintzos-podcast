#!/usr/bin/env python3
"""Build a podcast RSS feed from the audio listing of agia-triada-panorama.gr.

Only talks whose title mentions π. Ἰωάννης Γρίντζος are included.
Enclosures point straight at the monastery's mp3 files (no re-hosting).
"""
import html
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

BASE = "https://agia-triada-panorama.gr"
LIST_URL = BASE + "/audio/page/{n}/"
OUT = Path("docs/feed.xml")
SIZES = Path("sizes.json")          # cache: mp3 url -> byte length
FEED_URL = "https://charilaoss.github.io/grintzos-podcast/feed.xml"
COVER_URL = "https://charilaoss.github.io/grintzos-podcast/cover.jpg"
UA = "grintzos-podcast-feed/1.0 (+https://github.com/CharilaosS/grintzos-podcast)"
ATHENS = timezone(timedelta(hours=3))

ITEM_RE = re.compile(
    r'<li class="audio-item" data-title="(?P<title>[^"]*)">.*?'
    r'data-audio-file="(?P<url>[^"]+)".*?'
    r'<span class="date">\s*(?P<date>[^<]*?)\s*</span>.*?'
    r'<span class="subtitle">\s*(?P<cat>[^<]*?)\s*</span>.*?'
    r'<span class="duration">\s*(?P<dur>[^<]*?)\s*</span>.*?'
    r'data-id="(?P<id>\d+)"',
    re.S,
)


def fetch(url, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    return urllib.request.urlopen(req, timeout=60)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def is_grintzos(title):
    return "γριντζ" in strip_accents(title)


def scrape():
    items, seen = [], set()
    n = 1
    while True:
        try:
            page = fetch(LIST_URL.format(n=n)).read().decode("utf-8", "replace")
        except Exception as e:
            print(f"page {n}: {e}", file=sys.stderr)
            break
        found = 0
        for m in ITEM_RE.finditer(page):
            found += 1
            url = urllib.parse.quote(m["url"].strip(), safe=":/%?=&")
            if url in seen:
                continue
            seen.add(url)
            items.append({
                "id": m["id"],
                "title": html.unescape(m["title"]).strip(),
                "url": url,
                "date": m["date"].strip(),
                "category": html.unescape(m["cat"]).strip(),
                "duration": m["dur"].strip(),
            })
        print(f"page {n}: {found} items", file=sys.stderr)
        if found == 0:
            break
        n += 1
    return items


def parse_date(s):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(hour=12, tzinfo=ATHENS)
        except ValueError:
            pass
    return None


def size_of(url, cache):
    if url in cache:
        return cache[url]
    try:
        with fetch(url, "HEAD") as r:
            n = int(r.headers.get("Content-Length") or 0)
    except Exception as e:
        print(f"HEAD {url}: {e}", file=sys.stderr)
        n = 0
    if n:
        cache[url] = n
    return n


def main():
    cache = json.loads(SIZES.read_text()) if SIZES.exists() else {}
    allitems = scrape()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(allitems, ensure_ascii=False, indent=1))
    items = [i for i in allitems if is_grintzos(i["title"])]
    if len(items) < 50:
        sys.exit(f"only {len(items)} items scraped, refusing to overwrite feed")

    for it in items:
        it["dt"] = parse_date(it["date"]) or datetime.now(ATHENS)
        it["num"] = int(m.group(1)) if (m := re.match(r"(\d+)\.", it["title"])) else 0
        it["size"] = size_of(it["url"], cache)
    SIZES.write_text(json.dumps(cache, indent=0, sort_keys=True))

    items.sort(key=lambda i: (i["dt"], i["num"]), reverse=True)

    now = format_datetime(datetime.now(timezone.utc))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>π. Ἰωάννης Γρίντζος — Ὁμιλίες</title>",
        f"<link>{BASE}/audio/</link>",
        f'<atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
        "<language>el</language>",
        "<description>Ὁμιλίες τοῦ π. Ἰωάννου Γρίντζου, ὅπως ἀναρτῶνται στὴν ἱστοσελίδα τοῦ Ἱεροῦ Ἡσυχαστηρίου Ἁγίας Τριάδος Πανοράματος Θεσσαλονίκης. Ἀνεπίσημο feed· τὰ ἀρχεῖα παίζουν ἀπευθείας ἀπὸ τὴν ἱστοσελίδα.</description>",
        "<itunes:author>π. Ἰωάννης Γρίντζος</itunes:author>",
        f'<itunes:image href="{COVER_URL}"/>',
        '<itunes:category text="Religion &amp; Spirituality"><itunes:category text="Christianity"/></itunes:category>',
        "<itunes:explicit>false</itunes:explicit>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        desc = f'{it["category"]} · {it["date"]} · {BASE}/audio/'
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<guid isPermaLink=\"false\">agia-triada-audio-{it['id']}</guid>",
            f"<link>{BASE}/audio/</link>",
            f"<pubDate>{format_datetime(it['dt'])}</pubDate>",
            f"<description>{escape(desc)}</description>",
            f'<enclosure url="{escape(it["url"])}" length="{it["size"]}" type="audio/mpeg"/>',
            f"<itunes:duration>{escape(it['duration'])}</itunes:duration>",
            f"<itunes:episode>{it['num']}</itunes:episode>" if it["num"] else "",
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(o for o in out if o != ""), encoding="utf-8")
    print(f"wrote {OUT} with {len(items)} items", file=sys.stderr)


if __name__ == "__main__":
    main()
