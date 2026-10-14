from datetime import date

import pytest
from fastapi.testclient import TestClient

from ai.copilot import (
    CONDENSE_PROMPT,
    HISTORY_ANSWER_CHARS,
    MAX_HISTORY,
    Turn,
    answer_question,
    condense_question,
)
from ai.index_filings import vector_literal
from api.app import app
from api.deps import get_chat_model, get_embedder, get_sentiment_model
from data.db import connect

PRIOR_ANSWER = "SENTINEL-PRIOR-ANSWER: Zetacorp had 1234 secret widgets [1]."


def vec(i):
    v = [0.0] * 384
    v[i] = 1.0
    return v


class RecordingEmbedder:
    name = "fake"
    dim = 384

    def __init__(self):
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return vec(0)


class RoutingLLM:
    """Answers each kind of request differently: the rewrite step, the search-expansion step, and the final answer."""

    name = "routing-llm"

    def __init__(self, rewrite="What are Zetacorp's biggest risks?", answer="Zeta has risk [1]."):
        self.rewrite, self.answer = rewrite, answer
        self.condense_prompts, self.answer_prompts, self.calls = [], [], []

    def generate(self, system, user, json_schema=None):
        if system == CONDENSE_PROMPT:
            self.calls.append("condense")
            self.condense_prompts.append(user)
            if isinstance(self.rewrite, Exception):
                raise self.rewrite
            return self.rewrite
        if system.startswith("Rewrite a question"):
            self.calls.append("expand")
            return ""
        self.calls.append("answer")
        self.answer_prompts.append(user)
        return self.answer


@pytest.fixture
def conn():
    with connect() as c:
        for sym, name in (("ZZCA", "Zetacorp Inc."), ("ZZCB", "Omegaware Ltd.")):
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, name))
        for acc, sym in (("0-ZH-A", "ZZCA"), ("0-ZH-B", "ZZCB")):
            c.execute(
                "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                "VALUES (%s, %s, '1', '10-K', %s, 'https://x', 't')", (acc, sym, date(2025, 1, 1)))
        for acc, text in (("0-ZH-A", "Zeta risk text"), ("0-ZH-B", "Omega risk text")):
            c.execute(
                "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
                "VALUES (%s, 0, 'Item 1A', %s, %s::vector, 'fake')", (acc, text, vector_literal(vec(0))))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM filings WHERE symbol IN ('ZZCA', 'ZZCB')")
        c.execute("DELETE FROM instruments WHERE symbol IN ('ZZCA', 'ZZCB')")
        c.commit()


HISTORY = [Turn("How many employees does Zetacorp have?", PRIOR_ANSWER, ("ZZCA",))]


def ask(conn, llm, question, history=HISTORY, **kw):
    emb = RecordingEmbedder()
    return answer_question(conn, emb, llm, question, history=history, expand=False, **kw), emb


def test_no_history_means_no_extra_model_call_and_no_interpretation(conn):
    llm = RoutingLLM()
    ans, _ = ask(conn, llm, "What are Zetacorp's risks?", history=[])
    assert "condense" not in llm.calls and ans.interpreted_question is None and ans.symbols == ["ZZCA"]


def test_a_follow_up_is_searched_and_answered_as_the_standalone_question(conn):
    llm = RoutingLLM(rewrite="What are Zetacorp's biggest risks?")
    ans, emb = ask(conn, llm, "And what about its biggest risks?")
    assert ans.interpreted_question == "What are Zetacorp's biggest risks?"
    assert ans.question == "And what about its biggest risks?"  # the user's own words are kept
    assert emb.queries == ["What are Zetacorp's biggest risks?"]
    assert llm.answer_prompts[0].endswith("Question: What are Zetacorp's biggest risks?")
    assert ans.symbols == ["ZZCA"] and ans.grounded


def test_earlier_answers_never_reach_the_prompt_that_writes_the_answer(conn):
    """Safety: history may only help understand the question. If it leaked into the answering prompt, an earlier
    answer (possibly wrong) could be used as evidence."""
    llm = RoutingLLM()
    ask(conn, llm, "And what about its biggest risks?")
    assert PRIOR_ANSWER.split(":")[0] in llm.condense_prompts[0]  # the rewrite step does see it
    for prompt in llm.answer_prompts:
        assert "SENTINEL-PRIOR-ANSWER" not in prompt and "1234 secret widgets" not in prompt
        assert "How many employees does Zetacorp have?" not in prompt


def test_an_unchanged_question_is_not_reported_as_reinterpreted(conn):
    llm = RoutingLLM(rewrite="  what are  ZETACORP's risks?  ")
    ans, _ = ask(conn, llm, "What are Zetacorp's risks?")
    assert ans.interpreted_question is None


def test_chosen_companies_win_over_anything_the_rewrite_names(conn):
    llm = RoutingLLM(rewrite="What are Zetacorp's biggest risks?")
    ans, _ = ask(conn, llm, "And its risks?", symbols=["ZZCB"])
    assert ans.symbols == ["ZZCB"]


def test_a_company_named_in_the_rewrite_is_found(conn):
    llm = RoutingLLM(rewrite="What are Omegaware's biggest risks?")
    ans, _ = ask(conn, llm, "And the other one?")
    assert ans.symbols == ["ZZCB"]


def test_last_company_is_carried_only_when_the_question_refers_back(conn):
    unnamed = RoutingLLM(rewrite="What are its biggest risks?")  # the rewrite failed to name the company
    assert ask(conn, unnamed, "And what about its biggest risks?")[0].symbols == ["ZZCA"]
    assert ask(conn, RoutingLLM(rewrite="Which company has the most risks?"), "Which company has the most risks?")[0].symbols == []


def test_a_new_company_is_not_overridden_by_the_previous_one(conn):
    llm = RoutingLLM(rewrite="How many employees does Omegaware have?")
    ans, _ = ask(conn, llm, "How many employees does Omegaware have?")
    assert ans.symbols == ["ZZCB"] and ans.interpreted_question is None


class TestCondense:
    def test_uses_only_the_last_three_turns_and_trims_answers_and_citations(self):
        turns = [Turn(f"Question number {i}?", f"Answer {i} " + "x" * 1000 + " [1][2]", ("ZZCA",)) for i in range(5)]
        llm = RoutingLLM(rewrite="Standalone question?")
        assert condense_question(llm, "Follow-up?", turns) == "Standalone question?"
        prompt = llm.condense_prompts[0]
        assert MAX_HISTORY == 3 and "Question number 1?" not in prompt and "Question number 2?" in prompt
        assert "[1]" not in prompt and "x" * (HISTORY_ANSWER_CHARS + 1) not in prompt
        assert prompt.endswith("Latest question: Follow-up?") and "about ZZCA" in prompt

    def test_cleans_up_a_chatty_reply(self):
        for reply in ('"What are Tesla\'s risks?"', "Rewritten question: What are Tesla's risks?\nBecause the user meant Tesla.",
                      "\n\nQuestion: What are Tesla's risks?"):
            assert condense_question(RoutingLLM(rewrite=reply), "its risks?", HISTORY) == "What are Tesla's risks?"

    @pytest.mark.parametrize("bad", ["", "  \n ", "ok", "x" * 301, RuntimeError("Ollama is down")])
    def test_falls_back_to_the_original_on_any_doubt(self, bad):
        assert condense_question(RoutingLLM(rewrite=bad), "its risks?", HISTORY) == "its risks?"

    def test_nothing_to_do_without_history(self):
        llm = RoutingLLM()
        assert condense_question(llm, "its risks?", []) == "its risks?" and llm.calls == []


# ---- through the HTTP API ----

class ApiLLM(RoutingLLM):
    def available(self):
        return True


@pytest.fixture
def client(conn):
    llm = ApiLLM()
    app.dependency_overrides[get_embedder] = lambda: RecordingEmbedder()
    app.dependency_overrides[get_chat_model] = lambda: llm
    app.dependency_overrides[get_sentiment_model] = lambda: "routing-llm"
    with TestClient(app) as c:
        c.llm = llm
        yield c
    app.dependency_overrides.clear()


def turn(**kw):
    return {"question": "How many employees does Zetacorp have?", "answer": PRIOR_ANSWER, "companies": ["ZZCA"], **kw}


def test_api_understands_a_follow_up_and_says_how(client):
    r = client.post("/api/copilot", json={"question": "And what about its biggest risks?", "history": [turn()]})
    assert r.status_code == 200
    body = r.json()
    assert body["interpreted_question"] == "What are Zetacorp's biggest risks?"
    assert body["companies"] == ["ZZCA"] and body["grounded"]
    assert all("SENTINEL" not in p for p in client.llm.answer_prompts)


def test_api_reports_no_interpretation_for_a_plain_question(client):
    body = client.post("/api/copilot", json={"question": "What are Zetacorp's risks?", "symbols": ["ZZCA"]}).json()
    assert body["interpreted_question"] is None and client.llm.calls.count("condense") == 0


@pytest.mark.parametrize("history", [
    [turn()] * 5,                                   # too many turns
    [turn(answer="x" * 2001)],                      # answer too long
    [turn(question="")],                            # empty question
    [turn(question="q" * 501)],                     # question too long
    [turn(companies=["bad$"])],                     # not a ticker
    [turn(companies=["AAPL"] * 6)],                 # too many companies
    [{"question": "only a question"}],              # missing answer
    "not a list",
])
def test_api_rejects_bad_history(client, history):
    r = client.post("/api/copilot", json={"question": "And its risks?", "history": history})
    assert r.status_code == 422 and client.llm.calls == []


def test_api_uppercases_tickers_in_history_and_accepts_empty_companies(client):
    r = client.post("/api/copilot", json={"question": "And its risks?", "history": [turn(companies=["zzca"]), turn(companies=[])]})
    assert r.status_code == 200
    assert "about ZZCA" in client.llm.condense_prompts[0] and "about no company" in client.llm.condense_prompts[0]


# ---- the safeguard for a bare pronoun ----

OLDER = Turn("What are Omegaware's risks?", "Omegaware has risk text.", ("ZZCB",))
LATEST = Turn("How many employees does Zetacorp have?", PRIOR_ANSWER, ("ZZCA",))


def test_a_bare_pronoun_means_the_most_recent_company_even_if_the_model_picks_an_older_one(conn):
    llm = RoutingLLM(rewrite="What about Omegaware's legal proceedings?")  # the model misread "its"
    ans, emb = ask(conn, llm, "What about its legal proceedings?", history=[OLDER, LATEST])
    assert ans.symbols == ["ZZCA"]
    assert ans.interpreted_question == "What about its legal proceedings? (assuming ZZCA)"  # says what it assumed
    assert emb.queries == ["What about its legal proceedings?"]  # searches the user's words, not the wrong rewrite
    assert "Omegaware" not in llm.answer_prompts[0]


@pytest.mark.parametrize("question,rewrite,expected", [
    ("What about the first one's legal proceedings?", "What about Omegaware's legal proceedings?", ["ZZCB"]),  # deliberate
    ("What about the other one's legal proceedings?", "What about Omegaware's legal proceedings?", ["ZZCB"]),
    ("How does it compare to Omegaware's?", "How does Zetacorp compare to Omegaware?", ["ZZCA", "ZZCB"]),  # names a company
    ("And Omegaware's legal proceedings?", "What are Omegaware's legal proceedings?", ["ZZCB"]),         # no pronoun
])
def test_the_safeguard_stays_out_of_the_way_when_going_back_is_deliberate(conn, question, rewrite, expected):
    ans, _ = ask(conn, RoutingLLM(rewrite=rewrite), question, history=[OLDER, LATEST])
    assert sorted(ans.symbols) == expected
    assert "assuming" not in (ans.interpreted_question or "")


def test_the_safeguard_accepts_a_rewrite_that_includes_the_recent_company(conn):
    llm = RoutingLLM(rewrite="How do Zetacorp's and Omegaware's risks compare?")
    ans, _ = ask(conn, llm, "How do they compare?", history=[OLDER, LATEST])
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"] and "assuming" not in (ans.interpreted_question or "")


def test_chosen_companies_are_never_second_guessed_by_the_safeguard(conn):
    llm = RoutingLLM(rewrite="What about Omegaware's legal proceedings?")
    ans, _ = ask(conn, llm, "What about its legal proceedings?", history=[OLDER, LATEST], symbols=["ZZCB"])
    assert ans.symbols == ["ZZCB"]


# ---- a bare switch to another company ("What about Tesla?") keeps the topic ----
#
# The rewrite step is told to leave a question alone when it switches company, so it returned "What about Tesla?"
# untouched and the answer was a random mix of Tesla's filings. The topic is carried over in code instead.


@pytest.mark.parametrize("question", [
    "What about Omegaware?", "And Omegaware?", "How about Omegaware?", "Omegaware?", "What about OMEGAWARE then?",
    "Ok, and what about ZZCB?", "What about Omegaware's?",
])
def test_a_bare_company_switch_asks_the_previous_question_about_the_new_company(conn, question):
    llm = RoutingLLM(rewrite=question)  # the model leaves it as written, which is the bug
    ans, emb = ask(conn, llm, question)
    assert ans.interpreted_question is not None
    assert ans.interpreted_question.replace("ZZCB", "Omegaware").replace("OMEGAWARE", "Omegaware") == (
        "How many employees does Omegaware have?")
    assert ans.symbols == ["ZZCB"]
    assert emb.queries == [ans.interpreted_question]
    assert ans.question == question  # the user's own words are kept
    assert "SENTINEL-PRIOR-ANSWER" not in llm.answer_prompts[0]  # still only the question is carried, never the answer


def test_the_new_company_is_written_as_the_user_typed_it(conn):
    ans, _ = ask(conn, RoutingLLM(rewrite="And ZZCB?"), "And ZZCB?")
    assert ans.interpreted_question == "How many employees does ZZCB have?"


def test_a_pronoun_in_the_previous_question_becomes_the_new_company(conn):
    history = [Turn("And what about its biggest risks?", PRIOR_ANSWER, ("ZZCA",))]
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Omegaware?"), "What about Omegaware?", history=history)
    assert ans.interpreted_question == "And what about Omegaware's biggest risks?" and ans.symbols == ["ZZCB"]


def test_a_chain_of_bare_switches_keeps_the_original_topic(conn):
    """The browser sends the questions as typed, so the earlier "What about Omegaware?" is itself bare."""
    history = [HISTORY[0], Turn("What about Omegaware?", "Omegaware has 5 employees.", ("ZZCB",))]
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Zetacorp?"), "What about Zetacorp?", history=history)
    assert ans.interpreted_question == "How many employees does Zetacorp have?" and ans.symbols == ["ZZCA"]


def test_nothing_is_swapped_when_the_previous_question_names_no_tracked_company(conn):
    history = [Turn("How many employees does Fakeco have?", PRIOR_ANSWER, ("ZZCC",))]  # not a tracked company
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Omegaware and ZZCA?"), "What about Omegaware and ZZCA?", history=history)
    assert ans.interpreted_question is None  # nothing tracked to swap out, so the question is left alone


@pytest.mark.parametrize("question,history", [
    ("What about Omegaware's legal proceedings?", HISTORY),   # it has a topic of its own
    ("What about Omegaware stock?", HISTORY),                 # so does this one
    ("What about Zetacorp?", HISTORY),                        # the same company again: nothing to switch
    ("What about that?", HISTORY),                            # names no company
    ("What about Omegaware?", [Turn("How do Zetacorp and Omegaware compare on risks?", PRIOR_ANSWER, ("ZZCA", "ZZCB"))]),  # two to swap
    ("What about Omegaware?", [Turn("Which company has the most risks?", "x", ("ZZCA",))]),  # nothing to swap in
])
def test_the_switch_rule_stays_out_of_the_way(conn, question, history):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question, history=history)
    assert ans.interpreted_question is None


def test_a_rewrite_that_did_something_is_trusted(conn):
    llm = RoutingLLM(rewrite="How many employees does Omegaware have?")
    ans, _ = ask(conn, llm, "And Omegaware?")
    assert ans.interpreted_question == "How many employees does Omegaware have?" and llm.calls.count("condense") == 1


def test_chosen_companies_are_never_second_guessed_by_the_switch_rule(conn):
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Omegaware?"), "What about Omegaware?", symbols=["ZZCA"])
    assert ans.symbols == ["ZZCA"] and ans.interpreted_question is None
