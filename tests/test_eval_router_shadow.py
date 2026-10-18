"""The shadow measurement for the router "second look" (DECISIONS: "Router second look"). It records what the router says about each
research question WITHOUT changing any answer, then scores several policies for "what to do when the keywords chose something
specific" offline, from the recording. Fake model only; nothing here touches a database."""
import json

import pytest

from ai.eval_market import CASES, SEALED, Case
from ai.eval_router_shadow import (
    POLICIES, SECONDS_PER_CALL, final_kinds, main, plan, record, report, route_from_json, route_to_json, score, shadow_cases,
)
from ai.market import detect_intent
from ai.router import ROUTER_SYSTEM, Route, evidence_kinds


def route(category="research", price=False, news=False, sentiment=False, figures=(), filings=False, advice=False):
    return Route(category, price, news, sentiment, frozenset(figures), filings, advice)


FILINGS = route(filings=True)
PRICE = route(price=True)

FALLING = "What does Apple say about falling demand in China?"             # the keywords say prices; it is a filings question
# The two questions below used to be keyword mistakes about "lately" (fixed in DECISIONS: "Router second look, 'lately'"), so they are
# stand-ins now: the keywords' route is real, and the tests only pretend the expected evidence is the one named in each comment.
LATELY = "How's Nvidia been performing recently?"                           # the keywords say prices and headlines; pretend: prices only
FILINGS_DEFAULT = "Has Apple pulled back from its high this year?"          # no keyword route: the filings default
STEADY = "What are people saying about Amazon lately?"                      # the keywords say headlines only; pretend: a price question


def kw(question):
    return evidence_kinds(detect_intent(question))


def test_the_fixture_questions_are_routed_as_these_tests_assume():
    assert kw(FALLING) == ["price"] and kw(LATELY) == ["price", "headline"] and kw(FILINGS_DEFAULT) == ["filing"]
    assert kw(STEADY) == ["headline"]


# ---- the policies: what to do when the keywords chose something specific ----


def test_every_policy_keeps_todays_behaviour_when_the_keywords_found_nothing():
    for policy in POLICIES:
        assert final_kinds(policy, FILINGS_DEFAULT, True, PRICE) == ["price"], policy            # the router decides, as it does now
        assert final_kinds(policy, FILINGS_DEFAULT, True, FILINGS) == ["filing"], policy


def test_today_never_second_guesses_a_specific_keyword_route():
    assert final_kinds("today", FALLING, True, FILINGS) == ["price"]
    assert final_kinds("today", LATELY, True, PRICE) == ["price", "headline"]


def test_replace_lets_the_model_overrule_a_specific_keyword_route():
    assert final_kinds("replace", FALLING, True, FILINGS) == ["filing"]
    assert final_kinds("replace", STEADY, True, PRICE) == ["price"]


def test_replace_to_filings_only_overrules_when_the_model_says_filings():
    assert final_kinds("replace-to-filings", FALLING, True, FILINGS) == ["filing"]
    assert final_kinds("replace-to-filings", STEADY, True, PRICE) == ["headline"]            # a price verdict does not replace headlines
    assert final_kinds("replace-to-filings", LATELY, True, PRICE) == ["price", "headline"]


def test_intersect_keeps_only_what_both_chose():
    assert final_kinds("intersect-else-router", LATELY, True, PRICE) == ["price"]            # drops the headlines the model did not want
    assert final_kinds("intersect-else-keywords", LATELY, True, PRICE) == ["price"]
    both = route(price=True, news=True)                                 # the model also wants headlines, and the question has "lately"
    assert final_kinds("intersect-else-router", LATELY, True, both) == ["price"]    # no news cue in the question: the model's news is dropped
    assert final_kinds("intersect-else-router", "What are the news and price moves for Apple lately?", True, both) == kw(
        "What are the news and price moves for Apple lately?")                       # a news cue: both agree, nothing is removed


def test_intersect_with_nothing_in_common_falls_back_as_named():
    assert final_kinds("intersect-else-router", FALLING, True, FILINGS) == ["filing"]
    assert final_kinds("intersect-else-keywords", FALLING, True, FILINGS) == ["price"]


@pytest.mark.parametrize("policy", sorted(POLICIES))
@pytest.mark.parametrize("question", [
    "What did Apple's 10-K say about falling demand?",              # a filing is named: the keyword route was deliberate
    "Why did Microsoft's revenue fall last quarter?",               # a quarter and "why"
    "Did Amazon cut its dividend when the stock fell?",             # dividends
    "What's Amazon's dividend yield?",                              # a ratio the app does not compute: decided in code
    "What is Nvidia's price-to-book ratio?",                        # the same, with no other guard word in it
    "What is Apple's debt-to-equity ratio?",
    "Should I buy Nvidia stock?",                                   # advice: decided in code
])
def test_questions_decided_in_code_or_held_to_the_filings_are_never_second_guessed(policy, question):
    assert final_kinds(policy, question, True, route(figures=["pe"], price=True, news=True)) == kw(question)


@pytest.mark.parametrize("policy", sorted(POLICIES))
def test_a_router_that_failed_leaves_the_keyword_route(policy):
    for q in (FALLING, FILINGS_DEFAULT, LATELY):
        assert final_kinds(policy, q, True, None) == kw(q)


def test_an_outside_verdict_never_changes_the_kinds():
    outside = route(category="outside", price=True)
    for policy in POLICIES:
        assert final_kinds(policy, FALLING, False, outside) == kw(FALLING)


def test_the_model_cannot_overrule_a_company_free_question_with_an_outside_verdict():
    """A recording keeps whether the case names a company: with none, the model's "outside" verdict is a verdict, not a route."""
    records = [{"name": "x", "question": FALLING, "expected": ["price"], "companies": [], "routes": [route_to_json(route(category="outside"))]}]
    assert score(records)["replace"]["x"] == [True]
    records[0]["companies"] = ["AAPL"]                                   # with a company named, "outside" is ignored and the model's filings stand
    assert score(records)["replace"]["x"] == [False]


def test_the_policies_are_exactly_these():
    assert sorted(POLICIES) == ["intersect-else-keywords", "intersect-else-router", "replace", "replace-to-filings", "today"]


# ---- the recording ----


def test_a_route_round_trips_through_json():
    r = route(price=True, news=True, figures=["eps", "pe"], filings=True, advice=True)
    assert route_from_json(json.loads(json.dumps(route_to_json(r)))) == r
    assert route_to_json(None) is None and route_from_json(None) is None


class ScriptedLLM:
    """Answers the router question from a table keyed by the question; anything unknown fails like an offline model."""

    name = "scripted"

    def __init__(self, table):
        self.table, self.calls = table, []

    def generate(self, system, user, json_schema=None):
        assert system == ROUTER_SYSTEM                                      # the shadow run asks only the router question
        self.calls.append(user)
        reply = self.table[user]
        if isinstance(reply, Exception):
            raise reply
        return json.dumps({"category": reply.category, "price": reply.prices, "news": reply.news, "sentiment": reply.sentiment,
                           "figures": sorted(reply.figures), "filings": reply.filings, "advice": reply.advice})


def case(name, question, evidence, companies=("AAPL",), history=()):
    return Case(name, "routing", question, frozenset(evidence), frozenset(companies), history=history)


def test_the_recording_has_one_route_per_repeat_and_a_failure_is_recorded_as_none():
    llm = ScriptedLLM({FALLING: FILINGS, LATELY: RuntimeError("offline")})
    cases = [case("a", FALLING, {"filing"}), case("b", LATELY, {"price"})]
    records = record(llm, cases, repeat=2)
    assert [r["name"] for r in records] == ["a", "b"] and len(llm.calls) == 4
    assert all(len(r["routes"]) == 2 for r in records)
    assert records[0]["routes"][0]["filings"] is True and records[1]["routes"] == [None, None]
    assert records[0]["expected"] == ["filing"] and records[0]["companies"] == ["AAPL"] and records[0]["question"] == FALLING


def test_two_cases_with_the_same_name_are_both_kept():
    """One older case name is used twice in the evaluation; scores are keyed by name, so a duplicate would silently drop a case."""
    llm = ScriptedLLM({FALLING: FILINGS, LATELY: PRICE})
    records = record(llm, [case("same", FALLING, {"filing"}), case("same", LATELY, {"price"})], repeat=1)
    assert len({r["name"] for r in records}) == 2 and records[0]["name"] == "same"
    assert sum(len(v) for v in score(records)["today"].values()) == 2


def test_the_plan_counts_every_case_once_per_group():
    cases = shadow_cases(CASES)
    assert len({c.name for c in cases}) < len(cases)                    # the evaluation does have a repeated name
    text = plan(cases, 3)
    dev = [c for c in cases if c.name.startswith("sl ")]
    older = [c for c in cases if not c.name.startswith("sl ")]
    assert f"development (sl): " in text and f"/{len(dev)}\n" in text + "\n" and f"/{len(older)}" in text


# ---- which cases are measured ----


def test_only_research_cases_without_a_follow_up_are_measured():
    picked = shadow_cases(CASES)
    assert picked and all(not c.history and c.evidence for c in picked)
    assert not any(c.history for c in picked) and not any(not c.evidence for c in picked)


def test_the_sealed_set_is_never_measured_whatever_is_passed():
    sealed_names = {c.name for c in SEALED}
    assert sealed_names and not sealed_names & {c.name for c in shadow_cases(CASES)}
    assert shadow_cases(SEALED) == []                                   # even when handed the sealed cases directly


def test_a_prefix_selects_a_group_of_cases():
    only = shadow_cases(CASES, only=("sl ",))
    assert only and all(c.name.startswith("sl ") for c in only)


# ---- scoring from a recording, offline ----


def records_for(routes_by_name):
    cases = {c.name: c for c in [
        case("falling", FALLING, {"filing"}), case("lately", LATELY, {"price"}), case("steady", STEADY, {"price"}),
        case("control", "How did Apple stock perform last week?", {"price"}),
    ]}
    return [
        {"name": n, "question": cases[n].question, "expected": sorted(cases[n].evidence), "companies": ["AAPL"],
         "routes": [route_to_json(r) for r in rs]}
        for n, rs in routes_by_name.items()
    ]


GOOD = {"falling": [FILINGS, FILINGS], "lately": [PRICE, PRICE], "steady": [PRICE, route(news=True)], "control": [PRICE, PRICE]}


def test_scoring_counts_one_pass_per_case_and_repeat():
    s = score(records_for(GOOD))
    assert s["today"]["falling"] == [False, False]                      # the keywords say prices; the question is about filings
    assert s["today"]["control"] == [True, True]
    assert s["replace"]["falling"] == [True, True] and s["replace"]["lately"] == [True, True]
    assert s["replace"]["steady"] == [True, False]                      # the second repeat: a news verdict with no news cue is dropped


def test_scoring_notices_a_policy_that_breaks_a_control():
    bad = dict(GOOD, control=[FILINGS, FILINGS])                        # the model is wrong on a question the keywords get right
    s = score(records_for(bad))
    assert s["today"]["control"] == [True, True] and s["replace"]["control"] == [False, False]
    assert s["intersect-else-keywords"]["control"] == [True, True]


def test_the_report_lists_gains_and_losses_against_today_by_name():
    bad = dict(GOOD, control=[FILINGS, FILINGS])
    text = report(records_for(bad))
    assert "replace" in text and "gains over today" in text and "losses against today" in text
    replace_block = text[text.index("replace\n"):]
    assert "falling" in replace_block.split("losses against today")[0]          # gained
    assert "control" in replace_block.split("losses against today")[1]          # lost


def test_the_report_gives_a_total_for_every_policy():
    text = report(records_for(GOOD))
    for policy in POLICIES:
        assert policy in text
    assert "8 case-runs" in text or "8 runs" in text


# ---- the command line ----


def test_the_plan_never_calls_the_model(capsys, monkeypatch):
    import ai.eval_router_shadow as shadow

    monkeypatch.setattr(shadow, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("the plan must not build a model")))
    assert main(["--plan"]) == 0
    out = capsys.readouterr().out
    assert "model calls" in out and "sealed" in out.lower() and "not touched" in out


def test_a_run_needs_an_output_file(capsys):
    with pytest.raises(SystemExit):
        main(["--run"])


def test_there_is_no_way_to_ask_for_the_sealed_set():
    with pytest.raises(SystemExit):
        main(["--plan", "--sealed"])


def test_the_plan_states_the_numbers_it_is_based_on():
    cases = shadow_cases(CASES)
    text = plan(cases, 2)
    assert f"model calls: {len(cases) * 2}" in text
    assert f"about {len(cases) * 2 * SECONDS_PER_CALL / 60:.0f} minutes at {SECONDS_PER_CALL} s per call" in text
    assert f"({len(SEALED)} cases are excluded" in text
    assert SECONDS_PER_CALL == 1.5


def test_scoring_a_saved_recording_can_be_limited_to_a_group(tmp_path, capsys):
    records = records_for(GOOD)
    records[0]["name"] = "sl falling"
    path = tmp_path / "rec.json"
    path.write_text(json.dumps({"model": "m", "repeat": 2, "seconds": 1, "records": records}), encoding="utf-8")
    assert main(["--score", str(path), "--only", "sl "]) == 0
    assert capsys.readouterr().out.startswith("1 cases, 2 case-runs")
    assert main(["--score", str(path)]) == 0
    assert capsys.readouterr().out.startswith("4 cases, 8 case-runs")
