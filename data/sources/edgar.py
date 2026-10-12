"""SEC EDGAR client: ticker -> CIK, recent filings, and filing text.

EDGAR requires a User-Agent that identifies you (name and contact email) and
asks callers to stay under 10 requests per second.
"""
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{document}"


@dataclass(frozen=True)
class FilingRef:
    accession_number: str
    cik: str
    form: str
    filed_at: date
    period_of_report: Optional[date]
    url: str


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text("\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


class EdgarClient:
    def __init__(self, user_agent: str, min_interval: float = 0.15):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self._min_interval = min_interval
        self._last_request = 0.0
        self._ticker_map: Optional[dict[str, str]] = None

    def _get(self, url: str) -> requests.Response:
        wait = self._min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        resp = self._session.get(url, timeout=60)
        self._last_request = time.monotonic()
        resp.raise_for_status()
        return resp

    def cik_for_ticker(self, symbol: str) -> Optional[str]:
        if self._ticker_map is None:
            data = self._get(TICKER_MAP_URL).json()
            self._ticker_map = {
                row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()
            }
        return self._ticker_map.get(symbol.upper())

    def list_filings(self, cik: str, forms: list[str], limit_per_form: int) -> list[FilingRef]:
        recent = self._get(SUBMISSIONS_URL.format(cik=cik)).json()["filings"]["recent"]
        counts = {form: 0 for form in forms}
        refs = []
        for i, form in enumerate(recent["form"]):
            if form not in counts or counts[form] >= limit_per_form:
                continue
            counts[form] += 1
            accession = recent["accessionNumber"][i]
            refs.append(
                FilingRef(
                    accession_number=accession,
                    cik=cik,
                    form=form,
                    filed_at=date.fromisoformat(recent["filingDate"][i]),
                    period_of_report=_date(recent["reportDate"][i] or None),
                    url=ARCHIVE_URL.format(
                        cik_int=int(cik),
                        accession_nodash=accession.replace("-", ""),
                        document=recent["primaryDocument"][i],
                    ),
                )
            )
        return refs

    def fetch_text(self, ref: FilingRef) -> str:
        return html_to_text(self._get(ref.url).text)
