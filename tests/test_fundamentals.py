from datetime import date

import pytest

from data.db import connect
from data.fundamentals import compute, format_report, load_facts, trailing, _periods
from data.ingest_fundamentals import ingest_fundamentals
from data.sources.edgar import Fact, parse_company_facts

TODAY = date(2026, 10, 12)
D = date.fromisoformat
B = 1e9


def fact(concept, start, end, value, accn="acc-1", form="10-K", filed="2026-01-30", unit="USD", taxonomy="us-gaap"):
    return Fact(taxonomy, concept, unit, D(start) if start else None, D(end), value, accn, form, D(filed))


def flow(concept, rows):
    return _periods([fact(concept, *r[:3], r[3], *(r[4:])) for r in rows], concept)


# ---- the trailing-twelve-month formula, pinned to figures read from real filings ----

def test_apple_net_income_matches_the_figures_in_its_filings():
    # Apple's 10-K (year to 2025-09-27) and 10-Qs; the 9-month figures were checked against the 10-Q text.
    periods = flow("NetIncomeLoss", [
        ("2024-09-29", "2025-09-27", 112_010e6, "a-fy25", "10-K", "2025-10-31"),
        ("2024-09-29", "2025-06-28", 84_544e6, "a-9m25", "10-Q", "2025-08-01"),
        ("2025-09-28", "2026-06-27", 101_464e6, "a-9m26", "10-Q", "2026-07-31"),
        ("2026-03-29", "2026-06-27", 29_789e6, "a-3m26", "10-Q", "2026-07-31"),  # a quarter ending the same day
    ])
    result, why = trailing(periods)
    assert why == "" and result.value == pytest.approx(128_930e6)
    assert result.period_end == D("2026-06-27")
    assert "9 months to 2026-06-27" in result.how and "ended 2025-09-27" in result.how
    assert result.growth == pytest.approx(101_464 / 84_544 - 1)
    assert set(result.accessions) == {"a-fy25", "a-9m26", "a-9m25"}


def test_nvidia_revenue_matches_its_10q():
    periods = flow("Revenues", [
        ("2025-01-27", "2026-01-25", 215_938e6, "n-fy", "10-K", "2026-02-25"),
        ("2025-01-27", "2025-07-27", 90_805e6, "n-h1-25", "10-Q", "2025-08-27"),
        ("2026-01-26", "2026-07-26", 177_837e6, "n-h1-26", "10-Q", "2026-08-26"),
        ("2026-04-27", "2026-07-26", 96_221e6, "n-q2", "10-Q", "2026-08-26"),
    ])
    result, _ = trailing(periods)
    assert result.value == pytest.approx(302_970e6) and result.growth == pytest.approx(0.9585, abs=1e-3)
    assert "6 months to 2026-07-26" in result.growth_label


def test_when_the_latest_filing_is_the_annual_report_that_year_is_the_figure():
    periods = flow("Revenues", [
        ("2024-07-01", "2025-06-30", 281e9, "m-24", "10-K", "2025-07-30"),
        ("2025-07-01", "2026-06-30", 331.8e9, "m-25", "10-K", "2026-07-29"),
    ])
    result, _ = trailing(periods)
    assert result.value == 331.8e9 and result.how == "the 12 months ending 2026-06-30"
    assert result.growth == pytest.approx(331.8 / 281 - 1)


def test_a_reported_twelve_month_figure_beats_a_shorter_period_ending_the_same_day():
    # Amazon's 10-Q includes a twelve-month column.
    periods = flow("NetIncomeLoss", [
        ("2025-07-01", "2026-06-30", 135.281e9, "z-ttm", "10-Q", "2026-07-31"),
        ("2026-01-01", "2026-06-30", 92.902e9, "z-h1", "10-Q", "2026-07-31"),
    ])
    result, _ = trailing(periods)
    assert result.value == 135.281e9 and "12 months" in result.how


def test_missing_pieces_give_a_reason_not_a_wrong_number():
    no_prior = flow("Revenues", [
        ("2025-01-01", "2025-12-31", 100, "x", "10-K", "2026-01-30"),
        ("2026-01-01", "2026-06-30", 60, "y", "10-Q", "2026-07-30"),
    ])
    result, why = trailing(no_prior)
    assert result is None and "same 6 months a year before 2026-06-30" in why
    no_year = flow("Revenues", [
        ("2025-01-01", "2025-06-30", 40, "x", "10-Q", "2025-07-30"),
        ("2026-01-01", "2026-06-30", 60, "y", "10-Q", "2026-07-30"),
    ])
    result, why = trailing(no_year)
    assert result is None and "last full year" in why
    assert trailing({})[0] is None


def test_a_restated_figure_replaces_the_original():
    periods = flow("NetIncomeLoss", [
        ("2025-01-01", "2025-12-31", 100, "orig", "10-K", "2026-01-30"),
        ("2025-01-01", "2025-12-31", 90, "restated", "10-K/A", "2026-05-01"),
    ])
    assert trailing(periods)[0].value == 90


# ---- the full calculation ----

def company(**drop):
    """A tidy calendar-year company: TTM revenue 120, net income 24, EPS 2.40, operating income 30 (all x1e9)."""
    rows = []

    def add(concept, fy, h1_now, h1_prior, unit="USD", scale=B):
        rows.extend([
            fact(concept, "2025-01-01", "2025-12-31", fy * scale, "fy25", "10-K", "2026-02-05", unit),
            fact(concept, "2025-01-01", "2025-06-30", h1_prior * scale, "h1-25", "10-Q", "2025-07-30", unit),
            fact(concept, "2026-01-01", "2026-06-30", h1_now * scale, "h1-26", "10-Q", "2026-07-30", unit),
        ])

    add("Revenues", 100, 60, 40)
    add("NetIncomeLoss", 20, 12, 8)
    add("EarningsPerShareDiluted", 2.0, 1.2, 0.8, "USD/shares", 1)
    add("OperatingIncomeLoss", 25, 15, 10)
    add("GrossProfit", 50, 30, 20)
    rows.append(fact("WeightedAverageNumberOfDilutedSharesOutstanding", "2026-01-01", "2026-06-30", 10 * B, "h1-26", "10-Q", "2026-07-30", "shares"))
    rows.append(fact("EntityCommonStockSharesOutstanding", None, "2026-07-20", 10.1 * B, "h1-26", "10-Q", "2026-07-30", "shares", "dei"))
    rows.append(fact("CommonStockSharesOutstanding", None, "2026-06-30", 10.05 * B, "h1-26", "10-Q", "2026-07-30", "shares"))
    return [r for r in rows if r.concept not in drop]


def run(facts, close=24.0, close_date=TODAY, today=TODAY):
    return compute("ZZFUN", facts, close, close_date, today)


def test_a_clean_company_gets_every_figure_and_no_cautions():
    f = run(company())
    assert f.available and f.cautions == []
    assert f.revenue.value == pytest.approx(120 * B) and f.net_income.value == pytest.approx(24 * B)
    assert f.diluted_eps.value == pytest.approx(2.4) and f.operating_income.value == pytest.approx(30 * B)
    assert (f.gross_margin, f.operating_margin, f.net_margin) == (pytest.approx(0.5), pytest.approx(0.25), pytest.approx(0.2))
    assert f.revenue.growth == pytest.approx(60 / 40 - 1)
    assert f.pe == pytest.approx(10.0) and f.market_value == pytest.approx(10.1 * B * 24)
    assert "cover page" in f.shares.source and f.period_end == D("2026-06-30")


def test_no_figures_means_not_available_with_a_reason():
    f = run([])
    assert not f.available and "foreign filer" in f.unavailable_reason
    assert "not available" in format_report(f)


def test_a_leftover_concept_is_not_used_when_a_current_one_exists():
    # Apple stopped using "Revenues" in 2018 and now uses RevenueFromContract...
    facts = [r for r in company() if r.concept != "Revenues"]
    for r in company():
        if r.concept == "Revenues":
            facts.append(fact("RevenueFromContractWithCustomerExcludingAssessedTax", str(r.period_start), str(r.period_end), r.value, r.accession_number, r.form, str(r.filed_at)))
    facts.append(fact("Revenues", "2017-10-01", "2018-09-29", 999 * B, "old", "10-K", "2018-11-05"))
    assert run(facts).revenue.value == pytest.approx(120 * B)


def test_a_missing_gross_profit_is_quiet_and_a_stale_one_is_ignored():
    f = run(company(GrossProfit=True))
    assert f.gross_margin is None and f.cautions == []
    stale = company(GrossProfit=True) + [fact("GrossProfit", "2023-01-01", "2023-12-31", 5 * B, "old", "10-K", "2024-02-01")]
    f = run(stale)
    assert f.gross_profit is None and f.gross_margin is None and f.cautions == []


def test_negative_earnings_have_no_pe():
    facts = [r for r in company() if r.concept != "EarningsPerShareDiluted"] + [
        fact("EarningsPerShareDiluted", "2025-01-01", "2025-12-31", -1.0, "fy25", "10-K", "2026-02-05", "USD/shares"),
        fact("EarningsPerShareDiluted", "2025-01-01", "2025-06-30", -0.5, "h1-25", "10-Q", "2025-07-30", "USD/shares"),
        fact("EarningsPerShareDiluted", "2026-01-01", "2026-06-30", -0.4, "h1-26", "10-Q", "2026-07-30", "USD/shares")]
    f = run(facts)
    assert f.diluted_eps.value == pytest.approx(-0.9) and f.pe is None and "negative" in f.pe_note


def test_no_price_means_no_market_value_and_a_caution():
    f = run(company(), close=None, close_date=None)
    assert f.market_value is None and f.pe is None and any("no stored price" in c for c in f.cautions)


def test_net_income_far_above_operating_income_is_flagged():
    facts = [r for r in company() if r.concept != "NetIncomeLoss"]
    for start, end, v, accn in (("2025-01-01", "2025-12-31", 40, "fy25"), ("2025-01-01", "2025-06-30", 8, "h1-25"), ("2026-01-01", "2026-06-30", 40, "h1-26")):
        facts.append(fact("NetIncomeLoss", start, end, v * B, accn, "10-K", "2026-02-05"))
    f = run(facts)  # net income 72 vs operating income 30
    assert any("2.4 times operating income" in c and "may flatter" in c for c in f.cautions)
    assert not any("operating income" in c for c in run(company()).cautions)


def test_a_share_count_far_from_the_earnings_average_is_flagged():
    facts = [r for r in company() if r.concept != "EntityCommonStockSharesOutstanding"]
    facts.append(fact("EntityCommonStockSharesOutstanding", None, "2026-07-20", 11.5 * B, "h1-26", "10-Q", "2026-07-30", "shares", "dei"))
    f = run(facts)
    assert any("differs from the latest average" in c and "15%" in c for c in f.cautions)


def test_the_balance_sheet_count_is_used_without_a_cover_page_and_says_so():
    f = run(company(EntityCommonStockSharesOutstanding=True))
    assert f.shares.value == 10.05 * B and "balance sheet at 2026-06-30" in f.shares.source
    assert any("balance sheet date" in c for c in f.cautions)


def test_an_old_cover_page_count_gives_way_to_a_newer_balance_sheet():
    facts = [r for r in company() if r.concept != "EntityCommonStockSharesOutstanding"]
    facts.append(fact("EntityCommonStockSharesOutstanding", None, "2025-01-20", 9.0 * B, "old", "10-K", "2025-02-01", "shares", "dei"))
    assert run(facts).shares.value == 10.05 * B


def test_old_figures_and_an_old_price_are_flagged():
    f = run(company(), today=date(2027, 3, 1), close_date=date(2026, 10, 12))
    assert any("latest reported period ended 2026-06-30, which is old" in c for c in f.cautions)
    assert any("stored price is from 2026-10-12" in c for c in f.cautions)


def test_a_period_mismatch_between_figures_is_flagged():
    facts = [r for r in company() if r.concept != "OperatingIncomeLoss"]
    for start, end, v, accn in (("2024-01-01", "2024-12-31", 20, "fy24"), ("2025-01-01", "2025-12-31", 25, "fy25")):
        facts.append(fact("OperatingIncomeLoss", start, end, v * B, accn, "10-K", "2026-02-05"))
    f = run(facts)
    assert any("operating income is for the period ending 2025-12-31, not 2026-06-30" in c for c in f.cautions)
    assert f.operating_margin is None


def test_the_report_shows_sources_and_cautions():
    text = format_report(run(company(EntityCommonStockSharesOutstanding=True)))
    assert "ZZFUN" in text and "revenue" in text and "the last full year (ended 2025-12-31)" in text
    assert "P/E" in text and "10.0" in text and "CAUTION:" in text


# ---- reading the SEC's JSON ----

def _sec_row(**kw):
    row = {"start": "2025-01-01", "end": "2025-12-31", "val": 100, "accn": "0001", "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-01-30"}
    row.update(kw)
    return row


def sec_data():
    return {"facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [_sec_row(), _sec_row(form="8-K", accn="0002"), _sec_row(end="2015-12-31", start="2015-01-01", accn="0003")]}},
            "SomethingNotWanted": {"units": {"USD": [_sec_row()]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [_sec_row(val=2.5)]}},
        },
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-07-20", "val": 5000, "accn": "0004", "form": "10-Q", "filed": "2026-07-30"}]}}},
    }}


def test_only_wanted_figures_from_10k_and_10q_in_range_are_read():
    facts = parse_company_facts(sec_data(), date(2019, 1, 1))
    assert sorted((f.concept, f.accession_number) for f in facts) == [
        ("EarningsPerShareDiluted", "0001"), ("EntityCommonStockSharesOutstanding", "0004"), ("Revenues", "0001")]
    assert next(f for f in facts if f.concept == "EntityCommonStockSharesOutstanding").period_start is None


def test_foreign_filers_vocabulary_yields_nothing():
    assert parse_company_facts({"facts": {"ifrs-full": {"Revenue": {"units": {"TWD": [_sec_row()]}}}}}, date(2019, 1, 1)) == []


# ---- storing them ----

A = "ZZFUN"


class FakeEdgar:
    def __init__(self, data):
        self.data, self.calls = data, 0

    def cik_for_ticker(self, symbol):
        return "0000000042"

    def company_facts(self, cik):
        self.calls += 1
        return self.data


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Fundamentals Co') ON CONFLICT DO NOTHING", (A,))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM financial_facts WHERE symbol = %s", (A,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (A,))
        c.commit()


def test_ingest_stores_the_figures_and_repeating_adds_nothing(conn):
    edgar = FakeEdgar(sec_data())
    assert ingest_fundamentals(conn, edgar, "zzfun", today=date(2026, 10, 12)) == 3
    assert ingest_fundamentals(conn, edgar, A, today=date(2026, 10, 12)) == 0
    assert conn.execute("SELECT cik FROM instruments WHERE symbol = %s", (A,)).fetchone()[0] == "0000000042"
    loaded = {f.concept: f for f in load_facts(conn, A)}
    assert loaded["EarningsPerShareDiluted"].value == 2.5 and loaded["EntityCommonStockSharesOutstanding"].period_start is None


def test_a_restatement_is_kept_as_its_own_row_and_the_newest_wins(conn):
    ingest_fundamentals(conn, FakeEdgar(sec_data()), A, today=date(2026, 10, 12))
    later = sec_data()
    later["facts"]["us-gaap"]["Revenues"]["units"]["USD"] = [_sec_row(val=95, accn="0009", form="10-K/A", filed="2026-06-01")]
    assert ingest_fundamentals(conn, FakeEdgar(later), A, today=date(2026, 10, 12)) == 1
    revenue = _periods([f for f in load_facts(conn, A) if f.concept == "Revenues"], "Revenues")
    assert len(revenue) == 1 and next(iter(revenue.values())).value == 95


def test_a_foreign_filer_stores_nothing_and_is_not_an_error(conn):
    edgar = FakeEdgar({"facts": {"ifrs-full": {"Revenue": {"units": {"TWD": [_sec_row()]}}}}})
    assert ingest_fundamentals(conn, edgar, A, today=date(2026, 10, 12)) == 0
    assert load_facts(conn, A) == []


def test_ingest_needs_a_known_company_and_a_cik(conn):
    with pytest.raises(ValueError, match="not in instruments"):
        ingest_fundamentals(conn, FakeEdgar(sec_data()), "ZZNOPE")

    class NoCik(FakeEdgar):
        def cik_for_ticker(self, symbol):
            return None

    with pytest.raises(ValueError, match="no SEC CIK"):
        ingest_fundamentals(conn, NoCik(sec_data()), A)
