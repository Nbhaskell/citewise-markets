"""The local question log and its review command (DECISIONS: "Question log").

Every question asked through the web app is appended to `logs/copilot_questions.jsonl` (this PC only, git-ignored), so the real questions the
owner asks, and the answers that looked wrong, can replace synthetic evaluation rounds. The write is the one approved server-side write besides
starting an add (owner approved 2026-10-19). It must never break an answer, it can be switched off with `COPILOT_LOG=off`, it keeps the
question and the answer and not the sources' text, and the test suite switches it off (tests/conftest.py) so no test touches the real file.
`python -m ai.review_questions` lists what was asked and marks the answers that look like misses.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from ai.question_log import log_answer, log_enabled, log_path
from ai.review_questions import flagged, load, main, signals

RESPONSE = {
    "question": "Has the media turned against Tesla?", "answer": "The sources indicate lawsuits [1].", "refused": False, "grounded": True,
    "companies": ["TSLA"], "evidence_kinds": ["filing"], "model_route": [], "unverified_numbers": [], "cautions": ["Some caution text."],
    "searches": ["a", "b"], "interpreted_question": None, "disclaimer": "d",
    "sources": [{"number": 1, "kind": "filing", "excerpt": "SECRET EXCERPT TEXT"}],
}


@pytest.fixture
def logfile(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "copilot_questions.jsonl"
    monkeypatch.setenv("COPILOT_LOG", "on")
    monkeypatch.setenv("COPILOT_LOG_FILE", str(path))
    return path


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- writing ----


def test_an_answer_is_appended_as_one_json_line(logfile):
    log_answer(RESPONSE, history_len=0)
    [rec] = lines(logfile)
    assert rec["question"] == RESPONSE["question"] and rec["answer"] == RESPONSE["answer"]
    for key in ("interpreted_question", "companies", "evidence_kinds", "model_route", "refused", "grounded", "unverified_numbers", "cautions"):
        assert rec[key] == RESPONSE[key], key


def test_the_parent_folder_is_created(logfile):
    assert not logfile.parent.exists()
    log_answer(RESPONSE, history_len=0)
    assert logfile.exists()


def test_each_call_adds_a_line_and_keeps_the_earlier_ones(logfile):
    log_answer(RESPONSE, history_len=0)
    log_answer({**RESPONSE, "question": "Second?"}, history_len=0)
    assert [r["question"] for r in lines(logfile)] == [RESPONSE["question"], "Second?"]


def test_the_time_is_utc_and_recent(logfile):
    log_answer(RESPONSE, history_len=0)
    when = datetime.fromisoformat(lines(logfile)[0]["ts"])
    assert when.utcoffset() == timedelta(0) and abs(datetime.now(timezone.utc) - when) < timedelta(minutes=1)


def test_a_follow_up_is_marked(logfile):
    log_answer(RESPONSE, history_len=2)
    log_answer(RESPONSE, history_len=0)
    first, second = lines(logfile)
    assert first["follow_up"] is True and second["follow_up"] is False


def test_the_number_of_sources_is_kept_but_not_their_text(logfile):
    log_answer(RESPONSE, history_len=0)
    assert lines(logfile)[0]["sources"] == 1
    assert "SECRET EXCERPT TEXT" not in logfile.read_text(encoding="utf-8")


def test_non_ascii_text_is_kept_readable(logfile):
    log_answer({**RESPONSE, "question": "Qu’est-ce que Tesla ?"}, history_len=0)
    assert "Qu’est-ce" in logfile.read_text(encoding="utf-8")


def test_whether_the_router_was_on_is_recorded(logfile, monkeypatch):
    monkeypatch.setenv("COPILOT_ROUTER", "off")
    log_answer(RESPONSE, history_len=0)
    monkeypatch.setenv("COPILOT_ROUTER", "model")
    log_answer(RESPONSE, history_len=0)
    assert [r["router"] for r in lines(logfile)] == [False, True]


# ---- the switch ----


@pytest.mark.parametrize("value", ["off", "OFF", " off ", "0", "false", "no", "none"])
def test_every_off_value_writes_nothing(logfile, monkeypatch, value):
    monkeypatch.setenv("COPILOT_LOG", value)
    assert log_enabled() is False
    log_answer(RESPONSE, history_len=0)
    assert not logfile.exists()


@pytest.mark.parametrize("value", ["on", "1", "true", "", "   ", "banana"])
def test_on_values_and_blank_or_unrecognised_values_keep_it_on(logfile, monkeypatch, value):
    monkeypatch.setenv("COPILOT_LOG", value)
    assert log_enabled() is True
    log_answer(RESPONSE, history_len=0)
    assert logfile.exists()


def test_it_is_on_when_the_variable_is_not_set(monkeypatch):
    monkeypatch.delenv("COPILOT_LOG", raising=False)
    assert log_enabled() is True


def test_the_default_file_is_in_the_git_ignored_logs_folder(monkeypatch):
    monkeypatch.delenv("COPILOT_LOG_FILE", raising=False)
    assert log_path().parts[-2:] == ("logs", "copilot_questions.jsonl")


def test_the_test_suite_itself_runs_with_the_log_off():
    import os

    # tests/conftest.py sets this for the whole session, so no test can add to the real file; the tests above switch it on
    # only with a temporary file, through the `logfile` fixture
    assert os.environ.get("COPILOT_LOG") == "off"


# ---- it never breaks an answer ----


def test_a_path_that_cannot_be_written_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_LOG", "on")
    monkeypatch.setenv("COPILOT_LOG_FILE", str(tmp_path))          # a folder, not a file
    log_answer(RESPONSE, history_len=0)                              # no exception


def test_a_response_missing_fields_does_not_raise(logfile):
    log_answer({"question": "q"}, history_len=0)
    assert lines(logfile)[0]["question"] == "q"


# ---- signals: which answers look like misses ----


def rec(**kw):
    base = {"question": "q", "answer": "A fine answer [1].", "refused": False, "grounded": True, "unverified_numbers": [], "cautions": [],
            "model_route": [], "evidence_kinds": ["price"], "companies": ["TSLA"], "ts": "2026-10-19T12:00:00+00:00"}
    return {**base, **kw}


def test_a_clean_answer_has_no_signals():
    assert signals(rec()) == [] and not flagged(rec())


def test_a_refusal_is_flagged():
    assert signals(rec(refused=True)) == ["refused"] and flagged(rec(refused=True))


@pytest.mark.parametrize("text", [
    "The sources do not provide information about that.", "The sources provided do not include price data.",
    "The sources don't mention it.", "The provided sources do not contain a figure.", "The data does not cover July.",
    "It is not possible to determine that from the sources.", "That information is not available in the sources.",
    "That cannot be determined from the filings.", "We cannot determine it.", "The sources do not address that.",
    "The filings do not specify it.", "The data do not show it.", "The information does not specify the date.",
    "The filing doesn't address the plant.", "The data doesn't have July.", "The sources do not have that figure.",
])
def test_giving_up_phrases_are_flagged(text):
    assert "gave up" in signals(rec(answer=text)), text


@pytest.mark.parametrize("text", [
    "The stock rose 5% [1].", "Apple reports that its suppliers may fail [1].", "The 10-K does not discuss the plant, but it says X [1].",
])
def test_ordinary_answers_are_not_called_giving_up(text):
    assert "gave up" not in signals(rec(answer=text)), text


def test_an_answer_citing_nothing_is_flagged():
    assert "uncited" in signals(rec(grounded=False))
    assert "uncited" not in signals(rec(grounded=False, refused=True))        # a refusal is already "refused"


def test_unverified_numbers_are_flagged():
    assert "unverified numbers" in signals(rec(unverified_numbers=["17"]))


def test_a_route_the_model_chose_is_noted_but_not_a_flag():
    r = rec(model_route=["price"])
    assert "router chose" in signals(r) and not flagged(r)


def test_a_caution_is_noted_but_not_a_flag():
    r = rec(cautions=["Something."])
    assert "caution shown" in signals(r) and not flagged(r)


def test_flagged_means_refused_gave_up_uncited_or_unverified():
    assert all(flagged(rec(**kw)) for kw in (
        {"refused": True}, {"answer": "The sources do not include that."}, {"grounded": False}, {"unverified_numbers": ["1"]}))


# ---- reading the file ----


def write(path, records, extra=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([json.dumps(r) for r in records] + list(extra)) + "\n", encoding="utf-8")


def test_load_skips_blank_and_malformed_lines_and_counts_them(tmp_path):
    p = tmp_path / "q.jsonl"
    write(p, [rec(question="one")], extra=["", "{not json", '["a list"]'])
    records, bad = load(p)
    assert [r["question"] for r in records] == ["one"] and bad == 2


def test_load_of_a_missing_file_is_empty(tmp_path):
    assert load(tmp_path / "nope.jsonl") == ([], 0)


# ---- the command ----


def run(tmp_path, capsys, records, *args, extra=()):
    p = tmp_path / "q.jsonl"
    write(p, records, extra)
    code = main(["--path", str(p), *args])
    return code, capsys.readouterr().out


def test_the_command_lists_the_newest_last_n(tmp_path, capsys):
    records = [rec(question=f"question {i}", ts=f"2026-10-{10 + i:02d}T12:00:00+00:00") for i in range(5)]
    code, out = run(tmp_path, capsys, records, "--last", "2")
    assert code == 0 and "question 4" in out and "question 3" in out and "question 2" not in out


def test_the_default_is_the_last_twenty(tmp_path, capsys):
    records = [rec(question=f"question {i:02d}", ts=f"2026-09-{1 + i:02d}T12:00:00+00:00") for i in range(25)]
    _, out = run(tmp_path, capsys, records)
    assert "question 24" in out and "question 05" in out and "question 04" not in out


def test_since_keeps_only_that_day_and_later(tmp_path, capsys):
    records = [rec(question="old one", ts="2026-10-01T12:00:00+00:00"), rec(question="new one", ts="2026-10-15T12:00:00+00:00")]
    _, out = run(tmp_path, capsys, records, "--since", "2026-10-10")
    assert "new one" in out and "old one" not in out


def test_since_includes_the_day_itself(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(question="that day", ts="2026-10-10T00:00:01+00:00")], "--since", "2026-10-10")
    assert "that day" in out


def test_a_bad_since_date_is_an_error_message_not_a_crash(tmp_path, capsys):
    code, out = run(tmp_path, capsys, [rec()], "--since", "last tuesday")
    assert code == 2 and "YYYY-MM-DD" in out


def test_flagged_only_hides_the_clean_ones(tmp_path, capsys):
    records = [rec(question="a clean one"), rec(question="a refused one", refused=True)]
    _, out = run(tmp_path, capsys, records, "--flagged")
    assert "a refused one" in out and "a clean one" not in out


def test_each_entry_shows_its_signals_and_the_answer_start(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(question="why?", answer="The sources do not include that.", model_route=["news"])])
    assert "why?" in out and "gave up" in out and "router chose" in out and "The sources do not include that." in out


def test_long_answers_are_cut_unless_full_is_asked_for(tmp_path, capsys):
    long = "word " * 200
    _, short_out = run(tmp_path, capsys, [rec(answer=long)])
    _, full_out = run(tmp_path, capsys, [rec(answer=long)], "--full")
    assert len(full_out) > len(short_out) and "..." in short_out and full_out.count("word") == 200


def test_the_summary_counts_questions_flags_refusals_and_bad_lines(tmp_path, capsys):
    records = [rec(), rec(refused=True), rec(answer="The sources do not provide it.", model_route=["price"])]
    _, out = run(tmp_path, capsys, records, extra=["{broken"])
    assert "3 questions" in out and "2 flagged" in out and "1 refused" in out and "1 router" in out and "1 unreadable" in out


def test_a_missing_file_says_nothing_is_logged_yet(tmp_path, capsys):
    code = main(["--path", str(tmp_path / "none.jsonl")])
    out = capsys.readouterr().out
    assert code == 0 and "No questions logged yet" in out


def test_an_empty_log_says_nothing_matched(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(question="x", ts="2026-10-01T00:00:00+00:00")], "--since", "2026-12-01")
    assert "No questions" in out


def test_a_record_without_a_time_is_still_shown(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [{k: v for k, v in rec(question="no time").items() if k != "ts"}])
    assert "no time" in out and "unknown time" in out


def test_how_a_follow_up_was_understood_is_shown_only_when_there_is_one(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(question="and its news?", interpreted_question="What is the news on Tesla?")])
    assert "understood as: What is the news on Tesla?" in out
    _, out = run(tmp_path, capsys, [rec(question="plain")])
    assert "understood as" not in out


def test_missing_companies_and_data_show_a_dash(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(companies=[], evidence_kinds=[])])
    assert "companies: -" in out and "data: -" in out


def test_companies_and_data_are_listed(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(companies=["TSLA", "AAPL"], evidence_kinds=["price", "headline"])])
    assert "companies: TSLA, AAPL" in out and "data: price, headline" in out


def test_last_zero_shows_everything(tmp_path, capsys):
    records = [rec(question=f"question {i:02d}", ts=f"2026-09-{1 + i:02d}T12:00:00+00:00") for i in range(25)]
    _, out = run(tmp_path, capsys, records, "--last", "0")
    assert "question 00" in out and "25 questions" in out


def test_since_and_flagged_and_last_work_together(tmp_path, capsys):
    records = [
        rec(question="old refused", refused=True, ts="2026-10-01T12:00:00+00:00"),
        rec(question="new clean", ts="2026-10-15T12:00:00+00:00"),
        rec(question="new refused A", refused=True, ts="2026-10-16T12:00:00+00:00"),
        rec(question="new refused B", refused=True, ts="2026-10-17T12:00:00+00:00"),
    ]
    _, out = run(tmp_path, capsys, records, "--since", "2026-10-10", "--flagged", "--last", "1")
    assert "new refused B" in out and "new refused A" not in out and "old refused" not in out and "new clean" not in out


def test_a_record_whose_time_cannot_be_read_is_left_out_by_since_but_shown_otherwise(tmp_path, capsys):
    odd = rec(question="odd time", ts="yesterday-ish")
    _, out = run(tmp_path, capsys, [odd], "--since", "2026-01-01")
    assert "No questions" in out
    _, out = run(tmp_path, capsys, [odd])
    assert "odd time" in out


def test_the_default_path_is_the_one_the_log_writes_to(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COPILOT_LOG_FILE", str(tmp_path / "x.jsonl"))
    write(tmp_path / "x.jsonl", [rec(question="from the default")])
    assert main([]) == 0 and "from the default" in capsys.readouterr().out


def test_since_includes_a_question_logged_exactly_at_midnight(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [rec(question="at midnight", ts="2026-10-10T00:00:00+00:00")], "--since", "2026-10-10")
    assert "at midnight" in out
