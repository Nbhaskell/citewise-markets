"""The "what changed" view: big moves, market-wide days, notable headlines, mood shifts, new filings."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.deps import get_sentiment_model
from data import changes as ch
from data.changes import Headline
from data.db import connect

LATEST = date(2026, 3, 13)
MODEL = "fake-llm"


def series_ending(last: date, closes: list[float]) -> list[tuple[date, float]]:
    """Closes on consecutive days, the last one on `last`."""
    return [(last - timedelta(days=len(closes) - 1 - i), c) for i, c in enumerate(closes)]


def wobble(n: int, pct: float, start: float = 100.0) -> list[float]:
    """n closes that alternate up and down by `pct` percent each day, so the typical daily move is `pct`."""
    out, price = [start], start
    for i in range(1, n):
        price *= 1 + (pct / 100 if i % 2 else -pct / 100)
        out.append(price)
    return out


def with_last_move(closes: list[float], pct: float) -> list[float]:
    return closes + [closes[-1] * (1 + pct / 100)]


# ---- daily moves and the window ----------------------------------------------------------------------------------


def test_daily_moves_are_each_close_against_the_one_before_oldest_first():
    moves = ch.daily_moves([(date(2026, 3, 3), 110.0), (date(2026, 3, 1), 100.0), (date(2026, 3, 2), 105.0)])
    assert [(m.prev_day, m.day) for m in moves] == [(date(2026, 3, 1), date(2026, 3, 2)), (date(2026, 3, 2), date(2026, 3, 3))]
    assert moves[0].pct == pytest.approx(5.0)
    assert moves[1].pct == pytest.approx((110 - 105) / 105 * 100)


def test_a_weekend_does_not_shorten_the_window():
    days = [date(2026, 3, 11), date(2026, 3, 12), date(2026, 3, 13), date(2026, 3, 16)]  # Wed, Thu, Fri, Mon
    series = {"A": [(d, 1.0) for d in days]}
    assert ch.window_dates(series, 2) == [date(2026, 3, 13), date(2026, 3, 16)]


def test_window_is_the_last_n_dates_that_have_prices():
    series = {"A": series_ending(LATEST, [1.0] * 10), "B": series_ending(LATEST - timedelta(days=1), [1.0] * 10)}
    dates = ch.window_dates(series, 3)
    assert dates == [LATEST - timedelta(days=2), LATEST - timedelta(days=1), LATEST]


# ---- big moves ---------------------------------------------------------------------------------------------------


def moves_for(closes_by_symbol, days=1):
    series = {s: series_ending(LATEST, c) for s, c in closes_by_symbol.items()}
    return ch.analyze_moves(series, ch.window_dates(series, days))


def test_a_move_is_measured_against_the_companys_own_usual_day():
    calm = with_last_move(wobble(70, 0.5), 3.5)  # usual day 0.5%: a 3.5% day is far out
    jumpy = with_last_move(wobble(70, 2.4), 4.0)  # usual day 2.4%: a 4% day is ordinary, the bar is 4.8%
    big, _ = moves_for({"CALM": calm, "JUMPY": jumpy})
    assert [b.symbol for b in big] == ["CALM"]
    assert big[0].typical_pct == pytest.approx(0.5, abs=0.01)
    assert big[0].threshold_pct == pytest.approx(3.0)  # the 3% floor beats twice 0.5%


def test_the_bar_is_twice_the_usual_move_when_that_is_higher_than_the_floor():
    big, _ = moves_for({"J": with_last_move(wobble(70, 2.4), 5.0), "K": with_last_move(wobble(70, 2.4), 4.5)})
    assert [b.symbol for b in big] == ["J"]
    assert big[0].threshold_pct == pytest.approx(4.8, abs=0.01)


def test_a_small_move_under_the_floor_is_not_listed_even_for_a_very_calm_company():
    big, _ = moves_for({"CALM": with_last_move(wobble(70, 0.2), 2.9)})
    assert big == []


def test_a_move_exactly_at_the_bar_counts():
    closes = [100.0] * 70 + [103.0]  # usual move 0 (flat), so the bar is the 3% floor
    big, _ = moves_for({"X": closes})
    assert len(big) == 1 and big[0].move.pct == pytest.approx(3.0)


def test_big_days_inside_the_window_do_not_raise_their_own_bar():
    closes = wobble(70, 0.5) + [110.0, 100.0, 110.0]  # three huge swings in a 3-day window
    big, _ = moves_for({"X": closes}, days=3)
    assert len(big) == 3 and big[0].typical_pct == pytest.approx(0.5, abs=0.01)


def test_a_long_run_of_big_days_inside_the_window_cannot_lift_the_bar():
    # 21 calm moves before the window, then 25 days swinging 6%. If those days counted toward "usual", the bar would
    # be 12% and none would be listed.
    swings = [100.0 * (1.06 if i % 2 == 0 else 1.0) for i in range(25)]
    big, _ = moves_for({"X": wobble(22, 0.5) + swings}, days=25)
    assert len(big) >= 24 and big[0].typical_pct == pytest.approx(0.5, abs=0.01)


def test_without_enough_history_the_floor_alone_applies_and_typical_is_unknown():
    big, _ = moves_for({"NEW": with_last_move(wobble(10, 0.5), 3.5)})
    assert len(big) == 1 and big[0].typical_pct is None and big[0].threshold_pct == 3.0


def test_moves_are_listed_newest_day_first_then_biggest():
    closes = wobble(70, 0.3) + [110.0, 100.0]
    big, _ = moves_for({"A": closes, "B": wobble(70, 0.3) + [103.5, 99.0]}, days=2)
    assert [(b.move.day, b.symbol) for b in big] == [
        (LATEST, "A"), (LATEST, "B"), (LATEST - timedelta(days=1), "A"), (LATEST - timedelta(days=1), "B")]


# ---- market-wide days --------------------------------------------------------------------------------------------


def six_companies(last_moves):
    return {f"C{i}": with_last_move(wobble(70, 0.3), pct) for i, pct in enumerate(last_moves)}


def test_a_day_when_nearly_everything_fell_is_one_market_event_not_several_stories():
    big, days = moves_for(six_companies([-4.0, -2.0, -1.5, -3.5, -2.5, 0.2]))
    assert [(d.direction, d.moved_that_way, d.companies) for d in days] == [("down", 5, 6)]
    assert all(b.market_wide for b in big) and len(big) >= 2


def test_a_split_market_is_not_a_market_wide_day():
    big, days = moves_for(six_companies([-4.0, -2.0, -1.5, 2.5, 2.0, 1.5]))
    assert days == [] and not any(b.market_wide for b in big)


def test_one_company_falling_alone_is_not_market_wide():
    big, days = moves_for(six_companies([-6.0, 0.1, -0.2, 0.3, 0.0, 0.2]))
    assert days == [] and len(big) == 1 and big[0].market_wide is False


def test_a_company_that_rose_on_a_down_day_is_not_marked_market_wide():
    big, days = moves_for(six_companies([-2.0, -2.0, -2.0, -2.0, -2.0, 6.0]))
    assert [d.direction for d in days] == ["down"]
    assert [(b.symbol, b.market_wide) for b in big] == [("C5", False)]


def test_too_few_companies_never_make_a_market_day():
    _, days = moves_for({"A": with_last_move(wobble(70, 0.3), -3.0), "B": with_last_move(wobble(70, 0.3), -3.0)})
    assert days == []


# ---- headlines ---------------------------------------------------------------------------------------------------


def hl(i, title, label="positive", symbol="X", at=datetime(2026, 3, 13, 15, 0, tzinfo=timezone.utc), publisher="Wire"):
    return Headline(f"id{i}", symbol, title, publisher, "https://x", at, label)


def test_notable_headlines_are_positive_or_negative_each_story_once_templates_out():
    rows = [
        hl(1, "X wins big deal - Wire", "positive"),
        hl(2, "X wins big deal", "positive", publisher="Other"),  # the same story from another outlet
        hl(3, "X faces probe", "negative"),
        hl(4, "X routine update", "neutral"),
        hl(5, "X Stock Price Today: $12.00", "positive"),  # quote page
        hl(6, "X Options Chain", "negative"),  # data-page template
        hl(7, "Unrelated firm news", "irrelevant"),
        hl(8, "X not scored yet", None),
    ]
    out = ch.notable_headlines(rows)
    assert len(out) == 1 and out[0]["symbol"] == "X"
    assert (out[0]["positive"], out[0]["negative"]) == (1, 1)
    assert {h.title for h in out[0]["items"]} == {"X wins big deal", "X faces probe"}  # the newest copy of a story is kept


def test_only_the_newest_few_per_company_are_shown_but_all_are_counted():
    rows = [hl(i, f"Story number {i}", "positive", at=datetime(2026, 3, 13, 10, i, tzinfo=timezone.utc)) for i in range(7)]
    out = ch.notable_headlines(rows, per_company=3)
    assert out[0]["positive"] == 7
    assert [h.title for h in out[0]["items"]] == ["Story number 6", "Story number 5", "Story number 4"]


def test_headlines_beside_a_move_are_that_days_stories_with_positive_and_negative_first():
    day = date(2026, 3, 13)
    rows = [
        hl(1, "Neutral item", "neutral", at=datetime(2026, 3, 13, 20, 0, tzinfo=timezone.utc)),
        hl(2, "Good item", "positive", at=datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc)),
        hl(3, "Yesterday item", "positive", at=datetime(2026, 3, 12, 23, 59, tzinfo=timezone.utc)),
        hl(4, "Tomorrow item", "positive", at=datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)),
        hl(5, "Off topic item", "irrelevant", at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)),
        hl(6, "Other company item", "positive", symbol="Y", at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)),
    ]
    assert [h.title for h in ch.headlines_on(rows, "X", day)] == ["Good item", "Neutral item"]


# ---- mood shifts -------------------------------------------------------------------------------------------------


def test_a_mood_shift_compares_the_last_week_with_the_week_before():
    week = {"X": {"positive": 14, "neutral": 4, "negative": 2}}  # +0.6
    two = {"X": {"positive": 16, "neutral": 20, "negative": 14}}  # before: 2 / 16 / 12 -> -0.3333
    out = ch.mood_shifts(week, two)
    assert out == [{"symbol": "X", "score_now": 0.6, "stories_now": 20, "score_before": -0.3333, "stories_before": 30}]


def test_a_small_change_or_too_few_stories_is_not_a_shift():
    assert ch.mood_shifts({"X": {"positive": 10, "neutral": 10}}, {"X": {"positive": 20, "neutral": 20}}) == []  # same
    assert ch.mood_shifts({"X": {"positive": 5, "neutral": 2}}, {"X": {"positive": 5, "neutral": 2, "negative": 9}}) == []  # 7 now
    assert ch.mood_shifts({"X": {"positive": 12}}, {"X": {"positive": 12}}) == []  # no earlier week at all


# ---- from the database -------------------------------------------------------------------------------------------

SYMS = ["ZZCHA", "ZZCHB", "ZZCHC"]


@pytest.fixture(scope="module")
def seeded():
    def clean(c):
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzch-%'")
        c.execute("DELETE FROM filings WHERE symbol LIKE 'ZZCH_'")
        c.execute("DELETE FROM prices_daily WHERE symbol LIKE 'ZZCH_'")
        c.execute("DELETE FROM instruments WHERE symbol LIKE 'ZZCH_'")

    with connect() as c:
        clean(c)
        for sym in SYMS:
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, f"{sym} Co"))
        # A and B: 70 calm days then a 5% rise on the latest day. C: the same, but its latest bar is a day older.
        for sym, last in [("ZZCHA", LATEST), ("ZZCHB", LATEST), ("ZZCHC", LATEST - timedelta(days=1))]:
            for d, close in series_ending(last, with_last_move(wobble(70, 0.4), 5.0 if sym != "ZZCHB" else -5.0)):
                c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, %s, 'fake')", (sym, d, close))
        # Filings: A filed on the latest day, B ten days earlier. `fetched_at` is deliberately "now" for both.
        for acc, sym, form, filed in [("0-ZZCH-A", "ZZCHA", "10-Q", LATEST), ("0-ZZCH-B", "ZZCHB", "10-K", LATEST - timedelta(days=10))]:
            c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, period_of_report, url, text) "
                      "VALUES (%s, %s, '1', %s, %s, %s, 'https://sec.example/f', 't')", (acc, sym, form, filed, filed))
        stories = [
            ("1", "ZZCHA", "ZZCHA jumps on a new contract", "positive", datetime(2026, 3, 13, 14, 0, tzinfo=timezone.utc)),
            ("2", "ZZCHA", "ZZCHA quote page - Stock Price Today", "positive", datetime(2026, 3, 13, 14, 5, tzinfo=timezone.utc)),
            ("3", "ZZCHA", "ZZCHA old story", "negative", datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)),
            ("4", "ZZCHB", "ZZCHB faces a probe", "negative", datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)),
            ("5", "ZZCHB", "ZZCHB routine note", "neutral", datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc)),
        ]
        for key, sym, title, label, at in stories:
            c.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                      "VALUES (%s, 'fake', %s, 'Wire', 'https://x', %s)", (f"fake:zzch-{key}", title, at))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:zzch-{key}", sym))
            c.execute("INSERT INTO news_sentiment (article_id, symbol, label, model) VALUES (%s, %s, %s, %s)",
                      (f"fake:zzch-{key}", sym, label, MODEL))
        c.commit()
    yield
    with connect() as c:
        clean(c)
        c.commit()


def build(days=1, mood=lambda n: {}):
    with connect() as c:
        return ch.build_changes(c, MODEL, days, mood, SYMS)


def test_the_window_ends_at_the_newest_stored_price_and_a_late_company_is_flagged(seeded):
    out = build()
    assert out["as_of"] == LATEST and out["window_start"] == LATEST
    assert out["stale"] == [{"symbol": "ZZCHC", "as_of": LATEST - timedelta(days=1)}]


def test_big_moves_carry_their_numbers_and_that_days_headlines(seeded):
    out = build()
    by_symbol = {m["symbol"]: m for m in out["moves"]}
    assert set(by_symbol) == {"ZZCHA", "ZZCHB"}  # ZZCHC has no bar for the latest day
    a = by_symbol["ZZCHA"]
    assert a["date"] == LATEST and a["change_pct"] == pytest.approx(5.0, abs=0.01)
    assert a["typical_pct"] == pytest.approx(0.4, abs=0.02) and a["threshold_pct"] == 3.0
    assert a["previous_date"] == LATEST - timedelta(days=1)
    assert [h["title"] for h in a["headlines"]] == ["ZZCHA jumps on a new contract"]  # the quote page is left out
    assert [h["title"] for h in by_symbol["ZZCHB"]["headlines"]] == ["ZZCHB faces a probe", "ZZCHB routine note"]
    assert by_symbol["ZZCHB"]["change_pct"] < 0
    assert out["market_days"] == []  # three companies is too few to call a market-wide day


def test_filings_use_the_filing_date_not_the_day_the_app_downloaded_them(seeded):
    assert [(f["symbol"], f["form"]) for f in build(days=1)["filings"]] == [("ZZCHA", "10-Q")]
    wide = build(days=30)  # 30 stored days reach back past the ten-day-old 10-K
    assert [(f["symbol"], f["form"]) for f in wide["filings"]] == [("ZZCHA", "10-Q"), ("ZZCHB", "10-K")]


def test_with_no_new_filings_the_newest_stored_one_is_still_reported(seeded):
    out = build(days=1)
    assert out["newest_filing"]["symbol"] == "ZZCHA" and out["newest_filing"]["filed_at"] == LATEST
    with connect() as c:
        out = ch.build_changes(c, MODEL, 1, lambda n: {}, ["ZZCHB"])
    assert out["filings"] == [] and out["newest_filing"]["form"] == "10-K"


def test_notable_headlines_count_each_story_once_and_skip_templates_and_old_stories(seeded):
    out = build(days=1)
    by_symbol = {c["symbol"]: c for c in out["headlines"]}
    assert (by_symbol["ZZCHA"]["positive"], by_symbol["ZZCHA"]["negative"]) == (1, 0)  # quote page and old story left out
    assert [i["title"] for i in by_symbol["ZZCHA"]["items"]] == ["ZZCHA jumps on a new contract"]
    assert (by_symbol["ZZCHB"]["positive"], by_symbol["ZZCHB"]["negative"]) == (0, 1)  # the neutral one isn't notable


def test_a_longer_window_reaches_further_back(seeded):
    out = build(days=30)
    a = {c["symbol"]: c for c in out["headlines"]}["ZZCHA"]
    assert (a["positive"], a["negative"]) == (1, 1)  # the March 1 story is within 30 stored days too


def test_mood_counts_are_asked_for_the_last_7_and_14_days_and_filtered_to_these_companies(seeded):
    asked = []

    def mood(n):
        asked.append(n)
        return {"ZZCHA": {"positive": 14, "neutral": 4, "negative": 2} if n == 7 else {"positive": 16, "neutral": 20, "negative": 14},
                "AAPL": {"positive": 99}}

    out = build(mood=mood)
    assert asked == [7, 14]
    assert [s["symbol"] for s in out["mood_shifts"]] == ["ZZCHA"]


def test_no_prices_at_all_gives_an_empty_but_valid_answer(seeded):
    with connect() as c:
        out = ch.build_changes(c, MODEL, 3, lambda n: {}, ["NOSUCH"])
    assert out["as_of"] is None and out["moves"] == [] and out["filings"] == [] and out["stale"] == []


# ---- the endpoint ------------------------------------------------------------------------------------------------


@pytest.fixture
def client():
    app.dependency_overrides[get_sentiment_model] = lambda: MODEL
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_the_endpoint_returns_the_documented_shape_and_includes_tracked_companies(seeded, client):
    res = client.get("/api/changes", params={"days": 30})
    assert res.status_code == 200
    body = res.json()
    assert body["days"] == 30 and body["rules"]["min_move_pct"] == 3.0
    for key in ("stale", "filings", "moves", "market_days", "headlines", "mood_shifts"):
        assert isinstance(body[key], list)


def test_the_endpoint_defaults_to_one_day_and_checks_its_input(seeded, client):
    assert client.get("/api/changes").json()["days"] == 1
    assert client.get("/api/changes", params={"days": 0}).status_code == 422
    assert client.get("/api/changes", params={"days": 31}).status_code == 422
    assert client.get("/api/changes", params={"days": "x"}).status_code == 422


def test_the_endpoint_only_reads(seeded, client):
    assert client.post("/api/changes").status_code == 405


# ---- "since I last looked" ---------------------------------------------------------------------------------------


def test_since_means_the_stored_dates_after_it_not_a_count_of_days():
    series = {"A": series_ending(LATEST, [1.0] * 10)}
    assert ch.window_dates(series, 1, since=LATEST - timedelta(days=3)) == [
        LATEST - timedelta(days=2), LATEST - timedelta(days=1), LATEST]
    assert ch.window_dates(series, 1, since=LATEST) == []  # nothing new since the last look
    assert ch.window_dates(series, 1, since=LATEST + timedelta(days=5)) == []  # a date in the future


def test_since_is_capped_at_the_newest_thirty_stored_dates():
    series = {"A": series_ending(LATEST, [1.0] * 80)}
    dates = ch.window_dates(series, 1, since=date(2000, 1, 1))
    assert len(dates) == ch.MAX_DAYS and dates[-1] == LATEST


def test_since_gives_the_same_window_as_the_matching_days(seeded):
    with connect() as c:
        by_since = ch.build_changes(c, MODEL, 1, lambda n: {}, SYMS, since=LATEST - timedelta(days=1))
    by_days = build(days=1)
    assert by_since["days"] == 1 and by_since["since"] == LATEST - timedelta(days=1)
    for key in ("as_of", "window_start", "moves", "filings", "headlines", "stale"):
        assert by_since[key] == by_days[key]


def test_since_the_newest_day_is_an_honest_empty_window_not_no_data(seeded):
    with connect() as c:
        out = ch.build_changes(c, MODEL, 1, lambda n: {}, SYMS, since=LATEST)
    assert out["days"] == 0 and out["as_of"] == LATEST and out["window_start"] is None
    assert out["moves"] == [] and out["market_days"] == [] and out["stale"] == []
    assert out["since"] == LATEST and out["newest_filing"]["filed_at"] == LATEST


def test_a_filing_after_the_newest_price_still_shows_when_the_window_has_no_prices(seeded):
    with connect() as c:
        c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, period_of_report, url, text) "
                  "VALUES ('0-ZZCH-LATE', 'ZZCHA', '1', '8-K', %s, %s, 'https://sec.example/f', 't')",
                  (LATEST + timedelta(days=1), LATEST))
        c.commit()
        try:
            out = ch.build_changes(c, MODEL, 1, lambda n: {}, SYMS, since=LATEST)
        finally:
            c.execute("DELETE FROM filings WHERE accession_number = '0-ZZCH-LATE'")
            c.commit()
    assert [f["form"] for f in out["filings"]] == ["8-K"]


def test_the_endpoint_takes_since_and_it_wins_over_days(seeded, client):
    body = client.get("/api/changes", params={"since": "2999-01-01", "days": 7}).json()
    assert body["days"] == 0 and body["since"] == "2999-01-01" and body["moves"] == []
    assert body["as_of"] is not None  # the newest stored date, not "no prices"
    assert client.get("/api/changes", params={"since": "not-a-date"}).status_code == 422
    assert client.get("/api/changes").json()["since"] is None
