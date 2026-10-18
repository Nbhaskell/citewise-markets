"""Showing that the router was used (DECISIONS: "Router visibility").

When the keyword rules find no route and the local model picks the evidence instead, the answer says so: `Answer.model_route` lists
the kinds of evidence the MODEL chose (in the API's order), and is empty whenever the keywords decided, the router was off or failed,
or the model chose nothing different from the keyword route. It says what the model chose, not what was found: "Looked at ..." still
says what the answer was written from. Same fake model and fixture company (ZZMA) as test_router.py.
"""
import pytest

from ai.market import Intent, detect_intent
from ai.router import changed_kinds
from test_market import conn  # noqa: F401  (conn is a fixture)
from test_router import UNRECOGNISED, RouterLLM, ask, reply

FILINGS = Intent()


# ---- changed_kinds: what the model chose, when it differs from the keyword route ----


def test_nothing_changed_means_nothing_to_say():
    assert changed_kinds(FILINGS, FILINGS) == []


@pytest.mark.parametrize("after, kind", [
    (Intent(prices=True, filings=False), "price"),
    (Intent(headlines=True, filings=False), "headline"),
    (Intent(headlines=True, sentiment=True, filings=False), "headline"),     # sentiment alone is never chosen: it rides on headlines
    (Intent(fundamentals=frozenset({"pe"}), filings=False), "fundamentals"),
])
def test_each_kind_the_model_chose_is_named(after, kind):
    assert kind in changed_kinds(FILINGS, after)


def test_sentiment_is_named_when_the_model_chose_it():
    assert changed_kinds(FILINGS, Intent(headlines=True, sentiment=True, filings=False)) == ["sentiment", "headline"]


def test_the_kinds_come_in_the_apis_order_with_filings_last():
    after = Intent(prices=True, headlines=True, sentiment=True, fundamentals=frozenset({"eps"}), filings=True)
    assert changed_kinds(Intent(prices=True, filings=False), after) == ["price", "fundamentals", "sentiment", "headline", "filing"]


def test_a_model_that_picked_the_same_kinds_changed_nothing():
    same = Intent(prices=True, headlines=True, filings=False)
    assert changed_kinds(same, Intent(prices=True, headlines=True, sentiment=False, filings=False)) == []


def test_a_figure_name_change_alone_is_not_a_new_kind():
    assert changed_kinds(Intent(fundamentals=frozenset({"pe"}), filings=False), Intent(fundamentals=frozenset({"eps"}), filings=False)) == []


def test_only_the_advice_flag_changing_is_not_a_change_of_evidence():
    assert changed_kinds(FILINGS, Intent(advice=True)) == []              # the buy/sell notice is shown on its own


def test_a_model_that_turned_the_prices_off_is_named_by_what_it_chose():
    assert changed_kinds(Intent(prices=True, filings=False), Intent(headlines=True, filings=False)) == ["headline"]


# ---- through the whole copilot ----


def test_a_price_route_is_reported(conn):
    ans, _ = ask(conn, RouterLLM(reply(price=True)), UNRECOGNISED)
    assert ans.model_route == ["price"] and not ans.refused


def test_several_kinds_are_reported_in_order(conn):
    q = "Are people reading anything notable about ZZMA?"
    ans, _ = ask(conn, RouterLLM(reply(price=True, news=True, figures=["pe"]), answer="Marketco wins big contract [1]."), q)
    assert ans.model_route == ["price", "fundamentals", "headline"]


def test_a_news_verdict_the_cue_filter_removed_is_not_reported(conn):
    ans, _ = ask(conn, RouterLLM(reply(price=True, news=True, sentiment=True)), UNRECOGNISED)      # no news word in the question
    assert ans.model_route == ["price"]


def test_nothing_is_reported_when_the_router_is_off(conn):
    llm = RouterLLM(reply(price=True))
    ans, _ = ask(conn, llm, UNRECOGNISED, router=False)
    assert "route" not in llm.calls and ans.model_route == []


def test_nothing_is_reported_when_the_model_chose_the_filings(conn):
    ans, _ = ask(conn, RouterLLM(reply(filings=True), answer="Marketco faces supply risk [1]."), UNRECOGNISED)
    assert ans.model_route == []                                          # the filings default, as the keywords had it


def test_nothing_is_reported_when_the_model_chose_nothing(conn):
    ans, _ = ask(conn, RouterLLM(reply(), answer="Marketco faces supply risk [1]."), UNRECOGNISED)
    assert ans.model_route == []


def test_nothing_is_reported_when_the_keywords_decided(conn):
    llm = RouterLLM(reply(news=True))
    ans, _ = ask(conn, llm, "How has ZZMA stock done this month?")
    assert "route" not in llm.calls and ans.model_route == []


@pytest.mark.parametrize("route", [RuntimeError("offline"), "garbage", reply(category="other")])
def test_nothing_is_reported_when_the_router_failed(conn, route):
    ans, _ = ask(conn, RouterLLM(route, answer="Marketco faces supply risk [1]."), UNRECOGNISED)
    assert ans.model_route == []


def test_a_writing_decline_reports_no_evidence_kinds(conn):
    ans, _ = ask(conn, RouterLLM(reply(category="writing", price=True)), "Put together some encouraging words for my team about ZZMA.")
    assert ans.refused and ans.model_route == []


def test_an_outside_verdict_reports_no_evidence_kinds(conn):
    ans, _ = ask(conn, RouterLLM(reply(category="outside", price=True), answer="Marketco faces supply risk [1]."), UNRECOGNISED)
    assert ans.model_route == []


def test_an_answer_with_no_company_still_says_what_the_model_chose(conn):
    # The model sent a question with no company to the prices, which is why the app asks "which company?": say so.
    q = "Has it pulled back from its high this year?"
    assert detect_intent(q) == FILINGS
    ans, _ = ask(conn, RouterLLM(reply(price=True)), q)
    assert ans.refused and ans.model_route == ["price"]


def test_a_refusal_before_the_router_has_nothing_to_report(conn):
    ans, _ = ask(conn, RouterLLM(reply(price=True)), "Draft an email to my boss about ZZMA's results.")
    assert ans.refused and ans.model_route == []


# ---- the command line says it too ----


def _cli(conn, monkeypatch, capsys, llm, router):
    from contextlib import nullcontext

    from ai import copilot
    from test_market import FakeEmbedder

    monkeypatch.setattr(copilot, "FastEmbedder", FakeEmbedder)
    monkeypatch.setattr(copilot, "get_llm", lambda: llm)
    monkeypatch.setattr(copilot, "connect", lambda: nullcontext(conn))
    monkeypatch.setenv("COPILOT_ROUTER", router)
    copilot.main([UNRECOGNISED, "--no-expand"])
    return capsys.readouterr().out


def test_the_command_line_names_what_the_model_chose(conn, monkeypatch, capsys):
    out = _cli(conn, monkeypatch, capsys, RouterLLM(reply(price=True, news=True, figures=["pe"])), "model")
    assert "chosen by the local model, not the keyword rules: price, fundamentals\n" in out      # the news verdict had no news cue, so it was dropped


def test_the_command_line_is_silent_about_the_model_when_it_chose_nothing_new(conn, monkeypatch, capsys):
    out = _cli(conn, monkeypatch, capsys, RouterLLM(reply(price=True), answer="Marketco faces supply risk [1]."), "off")
    assert "chosen by the local model" not in out
