"""Headlines from the public Google News RSS search feed.

Headlines only (no article text). Fine for prototyping; check Google's terms and
swap in a licensed news API before a public launch.
"""
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from .base import NewsItem

FEED_URL = "https://news.google.com/rss/search"
# Sites that flood results with auto-generated "Fund X bought N shares" posts and drown real news.
EXCLUDED_SITES = ("marketbeat.com",)


def parse_feed(xml_bytes: bytes, symbol: str, source_name: str = "google_news") -> list[NewsItem]:
    items = []
    for node in ET.fromstring(xml_bytes).findall("./channel/item"):
        guid = (node.findtext("guid") or node.findtext("link") or "").strip()
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = node.findtext("pubDate")
        if not (guid and title and link and pub):
            continue
        publisher = (node.findtext("source") or "").strip() or None
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        published_at = parsedate_to_datetime(pub)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        items.append(
            NewsItem(
                id=f"{source_name}:{guid}",
                source=source_name,
                symbol=symbol.upper(),
                title=title,
                publisher=publisher,
                url=link,
                published_at=published_at,
            )
        )
    return items


class GoogleNewsSource:
    name = "google_news"

    def get_news(self, symbol: str, company_name: Optional[str], days: int = 7) -> list[NewsItem]:
        query = f'"{company_name}" {symbol} stock' if company_name else f"{symbol} stock"
        exclusions = "".join(f" -site:{site}" for site in EXCLUDED_SITES)
        params = {"q": f"{query} when:{days}d{exclusions}", "hl": "en-US", "gl": "US", "ceid": "US:en"}
        resp = requests.get(
            f"{FEED_URL}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
        return parse_feed(resp.content, symbol, self.name)
