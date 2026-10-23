"""The model-based router (DECISIONS: "Model-based routing experiment").

Keyword rules decide which evidence a question needs (prices, headlines, sentiment, figures, filings). Every round of new wording missed
in the same places, so when the keywords find no specific route (the question would go to the filings only), the local model is asked
ONE question: what kind of question is this? Its answer is constrained to JSON and only picks among the routes that already exist. It
never names a company, never writes an answer, and never removes a notice the keyword rules attached; any failure leaves the keyword
route alone. Everything here uses a fake model; the fixture company ZZMA has prices, headlines and a filing (see test_market.py).
"""
import json

import pytest

from ai.copilot import ADVICE_CAUTION, CONDENSE_PROMPT, Turn, answer_question
from ai.market import MarketEvidence, detect_intent
from ai.router import ROUTER_SCHEMA, ROUTER_SYSTEM, Route, _parse, apply_route, ask_router, needs_router, router_enabled
from test_market import A, FakeEmbedder, conn  # noqa: F401  (conn is a fixture)


def reply(category="research", price=False, news=False, sentiment=False, figures=(), filings=False, advice=False):
    return json.dumps({"category": category, "price": price, "news": news, "sentiment": sentiment, "figures": list(figures),
                       "filings": filings, "advice": advice})


class RouterLLM:
    """A fake model: the router question gets `route` (a JSON string, or an Exception to raise), anything else gets `answer`."""

    name = "router-llm"

    def __init__(self, route=None, answer="Marketco closed at 499.00 on 2026-10-12 [1].", rewrite=None):
        self.route, self.answer, self.rewrite = route if route is not None else reply(), answer, rewrite
        self.router_prompts, self.schemas, self.calls = [], [], []

    def generate(self, system, user, json_schema=None):
        if system == ROUTER_SYSTEM:
            self.calls.append("route")
            self.router_prompts.append(user)
            self.schemas.append(json_schema)
            if isinstance(self.route, Exception):
                raise self.route
            return self.route
        if system == CONDENSE_PROMPT:
            self.calls.append("condense")
            return self.rewrite
        self.calls.append("answer")
        return self.answer


# ---- reading the model's reply ----


def test_a_valid_reply_becomes_a_route():
    llm = RouterLLM(reply(price=True, news=True, sentiment=True, figures=["pe", "eps"], filings=True, advice=True))
    assert ask_router(llm, "How is the mood?") == Route(
        "research", True, True, True, frozenset({"pe", "eps"}), True, True)


def test_the_question_and_nothing_else_goes_to_the_model_with_the_schema():
    llm = RouterLLM()
    ask_router(llm, "Has Apple pulled back from its high?")
    assert llm.router_prompts == ["Has Apple pulled back from its high?"] and llm.schemas == [ROUTER_SCHEMA]


def test_the_model_is_never_asked_to_name_a_company():
    assert set(ROUTER_SCHEMA["properties"]) == {"category", "price", "news", "sentiment", "figures", "filings", "advice"}
    assert set(ROUTER_SCHEMA["required"]) == set(ROUTER_SCHEMA["properties"])


@pytest.mark.parametrize("bad", [
    "", "not json", "[]", "null", "42", '{"category": "research"}',
    reply(category="other"),
    json.dumps({"category": "research", "price": "yes", "news": False, "sentiment": False, "figures": [], "filings": False, "advice": False}),
    json.dumps({"category": "research", "price": False, "news": False, "sentiment": False, "figures": "pe", "filings": False, "advice": False}),
    json.dumps({"category": "research", "price": False, "news": False, "sentiment": False, "figures": [1], "filings": False, "advice": False}),
    json.dumps({"category": 3, "price": False, "news": False, "sentiment": False, "figures": [], "filings": False, "advice": False}),
])
def test_a_reply_that_is_not_a_valid_route_is_ignored(bad):
    assert ask_router(RouterLLM(bad), "anything") is None


@pytest.mark.parametrize("text", ["", "not json", "[]", "null", "42", '"research"'])
def test_parsing_alone_returns_none_for_anything_that_is_not_an_object(text):
    assert _parse(text) is None


def test_a_model_that_fails_is_ignored():
    assert ask_router(RouterLLM(RuntimeError("model offline")), "anything") is None


def test_unknown_figure_names_are_dropped_and_whitespace_is_ignored():
    route = ask_router(RouterLLM("  " + reply(figures=["pe", "bogus", "revenue"]) + "\n"), "anything")
    assert route.figures == frozenset({"pe", "revenue"})


# ---- when to ask ----


@pytest.mark.parametrize("question,asked", [
    ("What are Nvidia's biggest risks?", True),               # the filings route, nothing specific found
    ("Has Apple pulled back from its high this year?", True),
    ("How has Nvidia stock done this month?", False),         # the keywords found a price route
    ("What's the latest news on Tesla?", False),
    ("What is Apple's P/E ratio?", False),
    ("What's Apple's dividend yield?", False),                # a ratio the app does not compute: answered in code
    ("Should I buy Nvidia?", False),                           # the buy/sell/hold notice is already attached by the keywords
    # deliberate filings routes: the keyword rules chose the filings on purpose, so the model is not asked to second-guess them
    ("How much revenue did Amazon report in its latest 10-K?", False),
    ("In its latest annual report, what total revenue did Microsoft report?", False),
    ("What did Nvidia's quarterly report say about margins?", False),
    ("What drove Tesla's jump in energy storage revenue this year?", False),
    ("Why did Apple's services revenue change?", False),
    ("How much did Apple pay out in dividends over the past year?", False),
    ("What's the dividend payout ratio for Microsoft?", False),
    ("Which segment grew fastest at Alphabet?", False),
    ("What were Apple's iPhone sales over the past year?", False),       # a product line: "sales" the keywords did not read as the company's total
    ("How are Nvidia's data center sales trending?", False),
    # but "the last four quarters" is the twelve-month stretch, not a request for one quarter's filing
    ("Did anyone at Amazon mention supply issues across the latest four quarters?", True),
])
def test_the_router_is_asked_only_when_the_keywords_found_no_specific_route(question, asked):
    assert needs_router(detect_intent(question), question) is asked, question


# ---- applying the route to the keyword intent ----


FILINGS_ONLY = detect_intent("What are Nvidia's biggest risks?")
NEWSY = "What is being said in the news?"


def test_a_price_route_replaces_the_filings_default():
    intent, declined = apply_route(FILINGS_ONLY, Route("research", True, False, False, frozenset(), False, False), has_company=True)
    assert (intent.prices, intent.headlines, intent.sentiment, intent.filings, intent.fundamentals) == (True, False, False, False, frozenset())
    assert declined is None


def test_news_and_sentiment_routes():
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, True, False, frozenset(), False, False), has_company=True, question=NEWSY)
    assert (intent.headlines, intent.sentiment, intent.filings, intent.prices) == (True, False, False, False)
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, False, True, frozenset(), False, False), has_company=True, question=NEWSY)
    assert (intent.headlines, intent.sentiment) == (True, True)       # sentiment is built from headlines, as the keyword rules do


@pytest.mark.parametrize("question", [
    "Does Microsoft intend to cash out of its Activision stake?",     # a business question: headlines are noise here
    "Has Apple pulled back from its high this year?",
    "Walk me through how Tesla behaved in recent weeks.",
    "",
])
def test_the_model_cannot_add_headlines_to_a_question_with_no_news_cue(question):
    route = Route("research", True, True, True, frozenset(), False, False)
    intent, _ = apply_route(FILINGS_ONLY, route, has_company=True, question=question)
    assert (intent.headlines, intent.sentiment) == (False, False) and intent.prices      # the price part of the verdict stands


@pytest.mark.parametrize("question", [
    "Anything noteworthy being said about Apple in the press today?", "What stories are circulating about Amazon?",
    "Are the articles about Amazon glowing or gloomy?", "Give me the mood of recent coverage on AMD.",
    "What are people reading about Google right now?", "Has the tone around Tesla improved?", "What sent Microsoft's stock into a nosedive?",
    "What was behind that drop?", "Is the sentiment souring?", "Is the headline count rising?",
])
def test_a_news_cue_lets_the_models_news_verdict_through(question):
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, True, False, frozenset(), False, False), has_company=True, question=question)
    assert intent.headlines and not intent.filings, question


def test_a_news_verdict_the_cue_filter_removed_leaves_the_filings_default():
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, True, True, frozenset(), False, False), has_company=True, question="")
    assert (intent.headlines, intent.sentiment, intent.prices, intent.filings) == (False, False, False, True)


def test_a_figures_route_carries_the_figure_names():
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, False, False, frozenset({"pe", "profit"}), False, False), has_company=True)
    assert intent.fundamentals == frozenset({"pe", "profit"}) and not intent.filings and intent.market


def test_several_routes_together_and_filings_kept_when_the_model_asks_for_them():
    intent, _ = apply_route(FILINGS_ONLY, Route("research", True, True, False, frozenset({"revenue"}), True, False), has_company=True, question=NEWSY)
    assert (intent.prices, intent.headlines, intent.fundamentals, intent.filings) == (True, True, frozenset({"revenue"}), True)


def test_a_route_that_chooses_nothing_leaves_the_keyword_intent_alone():
    assert apply_route(FILINGS_ONLY, Route("research", False, False, False, frozenset(), False, False), has_company=True) == (FILINGS_ONLY, None)


def test_no_route_leaves_the_keyword_intent_alone():
    assert apply_route(FILINGS_ONLY, None, has_company=True) == (FILINGS_ONLY, None)


def test_the_advice_flag_is_the_union_of_the_keywords_and_the_model():
    asked = detect_intent("Should I buy Nvidia?")
    assert asked.advice
    kept, _ = apply_route(asked, Route("research", False, False, False, frozenset(), True, False), has_company=True)
    assert kept.advice                                                                  # the model cannot take the notice away
    added, _ = apply_route(FILINGS_ONLY, Route("research", False, False, False, frozenset(), True, True), has_company=True)
    assert added.advice                                                                 # but it can add one


def test_fields_the_router_does_not_decide_are_kept():
    base = detect_intent("What's Apple's dividend yield? And what are its risks?")
    assert base.unstored
    intent, _ = apply_route(base, Route("research", True, False, False, frozenset(), False, False), has_company=True)
    assert intent.unstored == base.unstored


WRITING = Route("writing", False, False, False, frozenset(), False, False)


@pytest.mark.parametrize("question", [
    "Put together some encouraging words for my team.", "Compose a short cheer for the team.", "Help me phrase a polite note to my accountant.",
    "Write me a toast.", "Draft something for my boss.", "Can you word an email for me?", "Come up with a limerick.", "Make a speech.",
    "Create a slide deck.", "Send a message to my team.", "Give me a poem.", "Craft a caption.", "Produce a script.", "Rewrite this paragraph.",
    "I need a blog post.", "Translate that.", "Sing me something.", "Code a quick program.", "Build a resume.", "Get me a joke.",
    "Pen a haiku.", "Text my friend about it.",
])
def test_a_writing_verdict_with_a_writing_word_declines_even_with_a_company(question):
    assert apply_route(FILINGS_ONLY, WRITING, has_company=True, question=question)[1] == "writing"
    assert apply_route(FILINGS_ONLY, WRITING, has_company=False, question=question)[1] == "writing"


@pytest.mark.parametrize("question", [
    "Could Apple be a dependable long-term holding?",      # an advice question the model called writing: no writing word, so no decline
    "What are Nvidia's biggest risks?", "How is the stock doing?", "",
])
def test_a_writing_verdict_without_a_writing_word_is_ignored(question):
    assert apply_route(FILINGS_ONLY, WRITING, has_company=True, question=question) == (FILINGS_ONLY, None)


def test_an_outside_verdict_is_only_a_hint_and_only_without_a_company():
    outside = Route("outside", False, False, False, frozenset(), False, False)
    assert apply_route(FILINGS_ONLY, outside, has_company=False) == (FILINGS_ONLY, "outside")    # it never changes the route or declines up front
    assert apply_route(FILINGS_ONLY, outside, has_company=True) == (FILINGS_ONLY, None)         # a named company: research whatever the model thinks


# ---- switching it on ----


# On by default since 2026-10-19 (DECISIONS: "Router on by default"); COPILOT_ROUTER=off is the way back. Every off value has a question
# of its own, and so does every value that must NOT turn it off (a blank or unrecognised value keeps the default).
@pytest.mark.parametrize("value,on", [
    ("model", True), ("MODEL", True), ("on", True), ("1", True), ("true", True), (" On ", True),
    ("off", False), ("OFF", False), (" off ", False), ("0", False), ("false", False), ("no", False), ("none", False),
    ("", True), ("   ", True), ("banana", True),
])
def test_the_environment_variable_values(monkeypatch, value, on):
    monkeypatch.setenv("COPILOT_ROUTER", value)
    assert router_enabled(None) is on


def test_the_router_is_on_unless_switched_off(monkeypatch):
    monkeypatch.delenv("COPILOT_ROUTER", raising=False)
    assert router_enabled(None) is True and router_enabled(True) is True and router_enabled(False) is False
    monkeypatch.setenv("COPILOT_ROUTER", "model")
    assert router_enabled(None) is True and router_enabled(False) is False
    monkeypatch.setenv("COPILOT_ROUTER", "off")
    assert router_enabled(None) is False and router_enabled(True) is True


# ---- through the whole copilot (ZZMA has prices, headlines, a filing) ----

UNRECOGNISED = "Has ZZMA pulled back from its high this year?"       # no keyword rule reads this one: filings only


def test_the_fixture_question_really_is_unrecognised_by_the_keywords():
    assert needs_router(detect_intent(UNRECOGNISED))


def ask(conn, llm, question, router=True, history=None, symbols=None):
    emb = FakeEmbedder()
    return answer_question(conn, emb, llm, question, symbols=symbols, expand=False, router=router, history=history), emb


def test_without_the_router_nothing_changes(conn):
    llm = RouterLLM()
    ans, emb = ask(conn, llm, UNRECOGNISED, router=False)
    assert "route" not in llm.calls and emb.queries            # the filings were searched, as before


def test_a_price_route_sends_an_unrecognised_question_to_the_prices(conn):
    llm = RouterLLM(reply(price=True))
    ans, emb = ask(conn, llm, UNRECOGNISED)
    assert llm.calls == ["route", "answer"] and emb.queries == []        # no filing search
    assert [r.kind for r in ans.retrieved if isinstance(r, MarketEvidence)] == ["price"] and not ans.refused


def test_the_router_is_not_asked_when_the_keywords_found_a_route(conn):
    llm = RouterLLM(reply(news=True))
    ask(conn, llm, "How has ZZMA stock done this month?")
    assert "route" not in llm.calls


@pytest.mark.parametrize("question", [
    "Draft an email to my boss about ZZMA's results.",         # the keyword writing rule declines first
    "What did Bitcoin do this month?",                          # so does the outside-topics rule
    "How many stores does Zorblaxx operate?",                   # and the unknown-name rule
])
def test_the_router_is_not_asked_when_code_already_declined_the_question(conn, question):
    llm = RouterLLM(reply(price=True))
    ans, _ = ask(conn, llm, question)
    assert ans.refused and llm.calls == []


def test_a_writing_verdict_declines_before_the_answer_is_written(conn):
    llm = RouterLLM(reply(category="writing"))
    ans, emb = ask(conn, llm, "Put together some encouraging words for my team about ZZMA.")
    assert ans.refused and "doesn't write" in ans.text and llm.calls == ["route"] and emb.queries == []


class NothingMatches(FakeEmbedder):
    """A query that is orthogonal to every stored passage, so the relevance gate finds nothing."""

    def embed_query(self, text):
        self.queries.append(text)
        return [0.0, 1.0] + [0.0] * 382


def test_an_outside_verdict_does_not_stop_a_question_the_filings_can_answer(conn):
    llm = RouterLLM(reply(category="outside"), answer="Marketco faces supply risk [1].")
    ans, emb = ask(conn, llm, "What is a supply risk?")
    assert not ans.refused and emb.queries and llm.calls == ["route", "answer"]


def store_a_swiss_headline(conn):
    """`unknown_name` declines a capitalised name that appears in no stored text. These two questions are about "the Swiss franc", so
    "Swiss" has to be stored (a database with real headlines happens to have it; a fresh one does not). The conn fixture deletes ids
    that start with fake:zzm-."""
    conn.execute("INSERT INTO news_articles (id, source, title, url, published_at) VALUES ('fake:zzm-swiss', 'fake', %s, 'https://x/s', now())",
                 ("Swiss franc holds steady against the dollar",))


def test_an_outside_verdict_gives_the_clearer_message_when_nothing_relevant_is_found(conn):
    store_a_swiss_headline(conn)
    llm = RouterLLM(reply(category="outside"))
    emb = NothingMatches()
    ans = answer_question(conn, emb, llm, "Is the Swiss franc strengthening?", expand=False, router=True)
    assert ans.refused and "outside what this app covers" in ans.text and "couldn't find anything" not in ans.text


def test_without_an_outside_verdict_nothing_found_keeps_the_old_message(conn):
    store_a_swiss_headline(conn)
    llm = RouterLLM(reply(category="research", filings=True))
    ans = answer_question(conn, NothingMatches(), llm, "Is the Swiss franc strengthening?", expand=False, router=True)
    assert ans.refused and "couldn't find anything" in ans.text


def test_an_outside_verdict_is_ignored_when_a_company_is_named(conn):
    llm = RouterLLM(reply(category="outside"))
    ans, emb = ask(conn, llm, UNRECOGNISED)
    assert not ans.refused and emb.queries                        # the keyword route (filings) stands


@pytest.mark.parametrize("route", [RuntimeError("offline"), "garbage", reply(category="other")])
def test_a_router_that_fails_leaves_the_keyword_route(conn, route):
    llm = RouterLLM(route, answer="Marketco faces supply risk [1].")      # a filings answer: no price for the numbers check to flag
    ans, emb = ask(conn, llm, UNRECOGNISED)
    assert not ans.refused and emb.queries and llm.calls == ["route", "answer"]


def test_the_router_sees_only_the_standalone_question_never_the_history(conn):
    from ai.copilot import Turn

    history = [Turn("What are Marketco's biggest risks?", "SENTINEL-PRIOR-ANSWER: supply risk.", ("ZZMA",))]
    llm = RouterLLM(reply(price=True))
    ask(conn, llm, UNRECOGNISED, history=history)
    assert all("SENTINEL-PRIOR-ANSWER" not in p and "biggest risks" not in p for p in llm.router_prompts)


def test_the_router_sees_the_rewritten_question_not_the_words_typed(conn):
    history = [Turn("What are Marketco's biggest risks?", "Supply risk.", ("ZZMA",))]
    llm = RouterLLM(reply(price=True), rewrite=UNRECOGNISED)
    ask(conn, llm, "And has it pulled back?", history=history)
    assert llm.router_prompts == [UNRECOGNISED]


def test_an_advice_verdict_adds_the_notice(conn):
    llm = RouterLLM(reply(price=True, advice=True))
    ans, _ = ask(conn, llm, UNRECOGNISED)
    assert ADVICE_CAUTION in ans.cautions


def test_chosen_companies_are_never_second_guessed_by_the_router(conn):
    llm = RouterLLM(reply(price=True))
    ans, _ = ask(conn, llm, "Has it pulled back from its high this year?", symbols=[A])
    assert ans.symbols == [A]


# ---- every word of the news cue lets the model's news verdict through (found by breaking each alternative on purpose) ----


@pytest.mark.parametrize("word", [
    "news", "press", "headline", "headlines", "story", "stories", "article", "articles", "coverage", "report", "reports", "reported",
    "reporting", "said", "saying", "says", "say", "written", "write", "published", "publishing", "buzz", "chatter", "mood", "tone",
    "sentiment", "reading", "read", "talking", "talk", "discussed", "discussing", "opinion", "opinions", "view", "views", "think", "thinks",
    "feeling", "feel", "bullish", "bearish", "positive", "negative", "hostile", "glowing", "gloomy", "why", "behind", "drove", "driving",
    "driven", "caused", "causing", "sparked", "sent",
])
def test_each_news_cue_word_lets_the_verdict_through(word):
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, True, False, frozenset(), False, False), has_company=True,
                            question=f"Apple {word} lately?")
    assert intent.headlines, word


def test_what_happened_is_a_news_cue():
    intent, _ = apply_route(FILINGS_ONLY, Route("research", False, True, False, frozenset(), False, False), has_company=True,
                            question="What happened to Apple?")
    assert intent.headlines


def test_a_sentiment_verdict_needs_a_cue_as_well():
    route = Route("research", False, False, True, frozenset(), False, False)
    assert apply_route(FILINGS_ONLY, route, True, question="Apple lately?")[0].sentiment is False
    assert apply_route(FILINGS_ONLY, route, True, question="Apple mood lately?")[0].sentiment is True


@pytest.mark.parametrize("question", [
    "What did the 10-K say about margins?", "What did the 10-Q say?", "What does the annual report cover?", "What happened in the quarter?",
    "Tell me about the quarterly results.", "What are the fiscal year numbers?", "What about the segments?", "Which filings mention that?",
    "What did the earnings call say?", "Where is revenue by region?", "Why did costs rise?", "What drove the change?",
    "What caused that?", "iPhone sales this year?", "Sales trends?", "Dividends this year?", "What is the payout?", "Do they pay out much?", "Are they paying out more?",
])
def test_each_deliberate_filings_cue_keeps_the_model_out(question):
    from ai.router import deliberately_filings

    assert deliberately_filings(question), question


@pytest.mark.parametrize("question", [
    "How much did Amazon pocket in profit over its latest four quarters?", "What was revenue over the most recent four quarters?",
    "Profit across the recent four quarters?", "Revenue over the past 4 quarters?", "Revenue over the trailing four quarters?",
    "What are the biggest risks?", "How has the stock done?",
])
def test_the_twelve_month_quarters_phrase_is_not_a_filing_cue(question):
    from ai.router import deliberately_filings

    assert not deliberately_filings(question), question


# ---- the question reaches needs_router and apply_route from answer_question ----


def test_a_deliberate_filings_question_is_not_put_to_the_model_even_when_the_router_is_on(conn):
    llm = RouterLLM(reply(price=True), answer="Marketco faces supply risk [1].")
    ans, emb = ask(conn, llm, "What did ZZMA's 10-K say about margins?")
    assert "route" not in llm.calls and emb.queries


def test_a_news_verdict_reaches_the_headlines_when_the_question_has_a_news_cue(conn):
    llm = RouterLLM(reply(news=True), answer="Marketco wins big contract [1].")
    q = "Are people reading anything notable about ZZMA?"
    assert needs_router(detect_intent(q), q)
    ans, emb = ask(conn, llm, q)
    assert llm.calls == ["route", "answer"] and "headline" in {getattr(r, "kind", "") for r in ans.retrieved} and emb.queries == []


# ---- every word of the writing cue lets the model's writing verdict through ----


@pytest.mark.parametrize("word", [
    "writing", "wrote", "drafting", "composing", "creating", "making", "make", "generating", "preparing", "crafting", "producing", "pen",
    "phrasing", "word", "rephrasing", "rewriting", "put together", "come up with", "help me", "give me", "get me", "text", "send", "translate",
    "sing", "code", "build", "email", "emails", "letter", "letters", "memo", "memos", "message", "messages", "note", "notes", "post", "posts",
    "tweet", "tweets", "caption", "captions", "script", "scripts", "slide", "slides", "deck", "decks", "presentation", "presentations",
    "resume", "resumes", "cv", "cvs", "press release", "press releases", "newsletter", "newsletters", "toast", "toasts", "cheer", "cheers",
    "essay", "essays", "speech", "speeches", "poem", "poems", "song", "songs", "haiku", "haikus", "limerick", "limericks", "joke", "jokes",
    "rap", "raps", "riddle", "riddles", "story", "stories", "blog", "words", "program", "python", "sql",
])
def test_each_writing_cue_word_lets_the_verdict_through(word):
    assert apply_route(FILINGS_ONLY, WRITING, has_company=True, question=f"Apple {word} lately?")[1] == "writing", word
