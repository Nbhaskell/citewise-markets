"""How far back a question asks about, read from its words ("past month", "since March", "year to date"), and the
cautions about periods the stored data does not cover."""
import math
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Optional

from .topics import _WEEKDAY, year_start_comparison


@dataclass(frozen=True)
class Window:
    label: str
    days: Optional[int]  # calendar days back from the latest stored price; None means since the start of the year
    explicit: bool = False  # False when the question named no period and the default was used
    since: Optional[date] = None  # "since July": the first day of the window, which wins over `days` when pricing it
    unmet: Optional[str] = None  # a period the question named that no window here can match ("the end of last week")
    asked_day: Optional[str] = None  # "today" or "yesterday": checked against the newest stored close
    day: Optional[date] = None  # "on Thursday", "last Wednesday", "Thursday's close": the most recent such day before today, whose close is given


DEFAULT_WINDOW = Window("past month", 31)
_WINDOWS = [  # checked in order, so the specific forms win
    (r"year[-\s]to[-\s]date|\bytd\b|this\s+(?:calendar\s+)?year|so\s+far\s+this\s+year|year\s+so\s+far|"
     r"(?:start|beginning)\s+of\s+(?:the\s+|this\s+)?year|since\s+(?:january|jan\b)|since\s+new\s+year",
     Window("year to date", None, True)),
    (r"\b(?:5|five)[-\s]years?\b", Window("past 5 years", 1830, True)),  # "5-year" as well as "5 years"
    (r"\b(?:6|six)[-\s]months?\b|\bhalf[-\s]year\b", Window("past 6 months", 183, True)),
    (r"\b(?:3|three)[-\s]months?\b|\bquarter\b|\b90\s+days\b", Window("past 3 months", 92, True)),
    (r"\b(?:12|twelve)[-\s]months?\b|\b(?:1|one)[-\s]year\b|52[-\s]?week|\byear\b", Window("past year", 366, True)),
    (r"\bmonth(?:ly)?\b|\b30\s+days\b", Window("past month", 31, True)),
    (r"\b(?:2|two)[-\s]weeks?\b|\bfortnight\b|\b14\s+days\b", Window("past 2 weeks", 14, True)),  # before "week", which it contains
    (r"\bweek(?:ly)?\b|\b(?:7|seven)\s+days\b", Window("past week", 7, True)),
    (r"\btoday\b|\byesterday\b|\bpast\s+day\b|\b(?:1|one)\s+day\b|\b24\s+hours\b", Window("past day", 1, True)),
]


_ONES = "one|two|three|four|five|six|seven|eight|nine"
_TEENS = "ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_BELOW_100 = rf"(?:(?:{_TENS})(?:[-\s](?:{_ONES}))?|{_TEENS}|{_ONES})"
# "ninety", "forty-five", "two hundred", "one hundred and twenty", "a hundred": a number written out, up to 999
_NUMBER_WORD = rf"(?:(?:a|{_ONES})\s+hundred(?:\s+(?:and\s+)?{_BELOW_100})?|hundred|{_BELOW_100})"
_NUM = rf"(?:\d{{1,4}}|{_NUMBER_WORD})"
_WORD_VALUES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen".split())}
_WORD_VALUES.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
_ROUGH_AMOUNTS = {"few": 3, "couple": 2, "several": 4}  # "the last few weeks": a guess, and the label says so
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MONTH_RE = r"(?:" + "|".join(_MONTHS) + r"|sept)"
_UNIT_RE = r"(trading\s+days?|sessions?|days?|weeks?|months?|quarters?|years?)"
_NUMBERED_PERIOD_RE = re.compile(
    rf"\b(?:last|past|previous)\s+(?:({_NUM})|(few|couple(?:\s+of)?|several))\s+{_UNIT_RE}\b", re.IGNORECASE,
)
# The lengths the app has always used for these, so a number written out in words keeps its old label and length.
_CANONICAL = {
    (1, "day"): Window("past day", 1, True), (7, "day"): Window("past week", 7, True),
    (14, "day"): Window("past 2 weeks", 14, True), (30, "day"): Window("past month", 31, True),
    (90, "day"): Window("past 3 months", 92, True),
    (1, "week"): Window("past week", 7, True), (2, "week"): Window("past 2 weeks", 14, True),
    (1, "month"): Window("past month", 31, True), (3, "month"): Window("past 3 months", 92, True),
    (6, "month"): Window("past 6 months", 183, True), (12, "month"): Window("past year", 366, True),
    (1, "year"): Window("past year", 366, True), (5, "year"): Window("past 5 years", 1830, True),
    (1, "quarter"): Window("past 3 months", 92, True),
}
# A trading day is about 5 of every 7 calendar days, so 10 sessions reach back about 14 calendar days.
_UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.5, "quarter": 91.5, "year": 366.0, "session": 1.4}
MAX_NUMBERED_DAYS = 3660
_AGO_PERIOD_RE = re.compile(rf"\b({_NUM})\s+{_UNIT_RE}\s+ago\b", re.IGNORECASE)
# "a year and a half", "two and a half years": exact, with the half in the label
_HALF_PERIOD_RES = (
    re.compile(rf"\b(an?|last|past|previous|{_NUM})\s+(year|month|week|quarter)s?\s+and\s+a\s+half\b", re.IGNORECASE),
    re.compile(rf"\b({_NUM})\s+and\s+a\s+half\s+(year|month|week|quarter)s?\b", re.IGNORECASE),
)
_DECADE_RE = re.compile(r"\b(?:last|past|previous)\s+decade\b", re.IGNORECASE)
_DECADE = Window("past 10 years", 3660, True)


def _to_int(raw: str) -> int:
    """"18", "ninety", "forty-five", "two hundred", "a hundred", "one hundred and twenty"."""
    raw = raw.lower().strip()
    if raw.isdigit():
        return int(raw)
    total = current = 0
    for token in re.split(r"[-\s]+", raw):
        if token == "and":
            continue
        if token == "a":
            current = 1
        elif token == "hundred":
            total += (current or 1) * 100
            current = 0
        else:
            current += _WORD_VALUES[token]
    return total + current


def _unit_key(unit: str) -> str:
    unit = unit.lower()
    return "session" if unit.startswith(("trading", "session")) else unit.rstrip("s")


def _numbered_period(question: str) -> Optional[Window]:
    """"the last four weeks", "past ninety days", "the last few weeks", "six weeks ago", "a year and a half", "past decade",
    "the last 8 quarters", "the last 10 trading days". None when the number is out of range."""
    if _DECADE_RE.search(question):
        return _DECADE
    for half in _HALF_PERIOD_RES:
        if h := half.search(question):
            n, unit = _to_int("1" if h.group(1).lower() in ("a", "an", "last", "past", "previous") else h.group(1)) + 0.5, h.group(2).lower()
            return Window(f"past {n:g} {unit}s", int(round(n * _UNIT_DAYS[unit])), True)
    m = _NUMBERED_PERIOD_RE.search(question)
    if m:
        number, rough, unit = m.group(1), m.group(2), _unit_key(m.group(3))
    elif a := _AGO_PERIOD_RE.search(question):  # "than it was six weeks ago": the window back to then
        number, rough, unit = a.group(1), None, _unit_key(a.group(2))
    else:
        return None
    if rough:  # few / couple / several
        word = re.sub(r"\s+of$", "", rough.lower())
        n, note = _ROUGH_AMOUNTS[word], f" (reading '{word}' as {_ROUGH_AMOUNTS[word]})"
    else:
        n, note = _to_int(number), ""
    if n < 1 or n * _UNIT_DAYS[unit] > MAX_NUMBERED_DAYS:
        return None
    if not note and (n, unit) in _CANONICAL:
        return _CANONICAL[(n, unit)]
    if unit == "session":
        days = int(math.ceil(n * _UNIT_DAYS[unit]))
        return Window(f"past {n} trading day{'' if n == 1 else 's'} (about {days} calendar day{'' if days == 1 else 's'})", days, True)
    return Window(f"past {n} {unit}{'' if n == 1 else 's'}{note}", int(round(n * _UNIT_DAYS[unit])), True)


_SINCE_YEAR_RE = re.compile(r"\bsince\s+(?:the\s+(?:start|beginning)\s+of\s+)?((?:19|20)\d\d)\b", re.IGNORECASE)


def _since_year(question: str, today: date) -> Optional[Window]:
    """"since 2024" (or "since the start of 2024"): from January 1 of that year. This year is year to date; a year that has not
    come is not read (the caller flags it)."""
    m = _SINCE_YEAR_RE.search(question)
    if not m:
        return None
    year = int(m.group(1))
    if year == today.year:
        return _WINDOWS[0][1]
    if year > today.year:
        return None
    since = date(year, 1, 1)
    return Window(f"since January 1, {year}", (today - since).days, True, since=since)


_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_SINCE_WEEKDAY_RE = re.compile(rf"\bsince\s+({_WEEKDAY})\b", re.IGNORECASE)


def _since_weekday(question: str, today: date) -> Optional[Window]:
    """"since Monday": from the most recent Monday before today (a week ago when today is one). "Since last Monday" is left
    alone: on a Monday it could mean either, so it is flagged instead."""
    m = _SINCE_WEEKDAY_RE.search(question)
    if not m:
        return None
    name = m.group(1).lower()
    days_back = (today.weekday() - _WEEKDAY_NAMES.index(name)) % 7 or 7
    since = today - timedelta(days=days_back)
    return Window(f"since {name.capitalize()} {since}", days_back, True, since=since)


_SINCE_MONTH_RE = re.compile(
    rf"\bsince\s+(?:(?:the\s+)?(?:start|beginning)\s+of\s+|(?P<middle>(?:the\s+)?middle\s+of\s+|mid[\s-]+))?(?P<month>{_MONTH_RE})\b",
    re.IGNORECASE,
)


def _since_month(question: str, today: date) -> Optional[Window]:
    """"since July": from the first of that month, this year, or last year when the month has not come yet. January is
    left to the year-to-date window, which is the same thing. "Since the middle of August" (or "mid-August") starts on the
    15th, and the label says that is how it was read. "Since the end of August" and "late August" are not read: nothing in the
    daily closes marks them, and a guess of the 25th would be a made-up period."""
    m = _SINCE_MONTH_RE.search(question)
    if not m:
        return None
    middle = m.group("middle") is not None
    name = m.group("month").lower()
    month = 9 if name == "sept" else _MONTHS.index(name) + 1
    if month == 1 and not middle:
        return None
    day = 15 if middle else 1
    since = date(today.year, month, day)
    if since > today:  # the month has not come yet this year (or its middle has not)
        since = date(today.year - 1, month, day)
    label = f"since {_MONTHS[month - 1].capitalize()} 15 (reading 'the middle' as the 15th)" if middle else f"since {_MONTHS[month - 1].capitalize()} 1"
    return Window(label, (today - since).days, True, since=since)


# Periods the stored daily closes cannot isolate: a day or a calendar stretch. The window used is the nearest one, and
# the answer is told (and the reader warned) that it is not the period asked. "last month" and "this week" are not here:
# people use them loosely for "the past month" and "the past week", and a warning on every one would be noise.
_UNMET_PATTERNS = [
    r"\b(?:the\s+)?end\s+of\s+(?:last|this|the)\s+(?:week|month|quarter|year)\b",
    r"\b(?:on|last)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    rf"\b(?:on\s+)?{_MONTH_RE}\s+\d{{1,2}}(?:st|nd|rd|th)?\b",
    rf"\b(?:in|during)\s+{_MONTH_RE}\b",
    r"\bq[1-4]\b|\b(?:first|second|third|fourth)\s+quarter\b",
    r"\b(?:in|during|for)\s+20\d\d\b",
]


def _unmet_period(question: str) -> Optional[str]:
    for pattern in _UNMET_PATTERNS:
        if m := re.search(pattern, question, re.IGNORECASE):
            return m.group(0)
    return None


# Periods that are named but that nothing above reads. Checked only when no window was read at all, so a question that fell
# to the default month says so (a caution on the answer) instead of passing the month off as the period asked. The last
# pattern is the net: "since" and up to four more words, which catches "since earnings", "since the election", "since the IPO".
_UNREAD_PATTERNS = [
    rf"\b(?:early|late)\s+{_MONTH_RE}\b|\b(?:the\s+)?(?:end|middle)\s+of\s+{_MONTH_RE}\b|\bmid[\s-]?{_MONTH_RE}\b",
    rf"\bbetween\s+(?:{_MONTH_RE}|20\d\d)\s+and\s+(?:{_MONTH_RE}|20\d\d)\b",
    rf"\bfrom\s+(?:{_MONTH_RE}|20\d\d)\s+(?:to|through|until)\s+(?:{_MONTH_RE}|20\d\d)\b",
    r"\b(?:over|during|throughout|across)\s+the\s+(?:summer|winter|spring|fall|autumn|holidays?|holiday\s+season)\b",
    r"\ball[-\s]time\b|\bsince\s+inception\b|\bthe\s+last\s+time\b",
    r"\bsince\s+[\w'’-]+(?:\s+[\w'’-]+){0,3}",
]


def _unread_period(question: str) -> Optional[str]:
    for pattern in _UNREAD_PATTERNS:
        if m := re.search(pattern, question, re.IGNORECASE):
            return m.group(0)
    return None


# One named weekday ("What was Microsoft's close last Wednesday?"): the most recent such day before today. "Since last Monday" is a range and
# stays flagged (it can mean either of two Mondays), so a weekday right after "since" is not read here.
_NAMED_DAY_RE = re.compile(
    rf"(?<!since )\b(?:on|last)\s+({_WEEKDAY})\b|\b({_WEEKDAY})['’]s\s+(?:close|closing)\b", re.IGNORECASE
)


def _named_day(question: str, today: date) -> Optional[date]:
    m = _NAMED_DAY_RE.search(question)
    if not m:
        return None
    name = (m.group(1) or m.group(2)).lower()
    return today - timedelta(days=(today.weekday() - _WEEKDAY_NAMES.index(name)) % 7 or 7)


def parse_window(question: str, today: Optional[date] = None) -> Window:
    today = today or date.today()
    window = _read_window(question, today)
    unmet = _unmet_period(question)
    day = _named_day(question, today)
    if day and unmet and re.fullmatch(rf"(?:on|last)\s+{_WEEKDAY}", unmet, re.IGNORECASE):
        unmet = None  # read as one day, so it is no longer a period the daily closes cannot isolate
    if not unmet and not window.explicit:
        unmet = _unread_period(question)
    asked = "today" if re.search(r"\btoday\b", question, re.IGNORECASE) else (
        "yesterday" if re.search(r"\byesterday\b", question, re.IGNORECASE) else None)
    if unmet or asked or day:
        window = replace(window, unmet=unmet, asked_day=asked, day=day)
    return window


def _read_window(question: str, today: date) -> Window:
    if year_start_comparison(question, today):
        return _WINDOWS[0][1]  # year to date
    if (
        (w := _since_month(question, today)) or (w := _since_year(question, today)) or (w := _since_weekday(question, today))
        or (w := _numbered_period(question))
    ):
        return w
    for pattern, window in _WINDOWS:
        if re.search(pattern, question, re.IGNORECASE):
            return window
    return DEFAULT_WINDOW


def period_cautions(window: Window, evidence: list, today: Optional[date] = None) -> list[str]:
    """Warnings, attached in code, for a period the question named that the price source does not cover. Only when a price
    source was given: with none, there is no wrong period to warn about."""
    today = today or date.today()
    prices = [e for e in evidence if e.kind == "price"]
    newest = [e.as_of for e in prices]
    if not newest:  # headlines only: the same warning for a period the news window cannot match
        if window.unmet and any(e.kind in ("headline", "sentiment") for e in evidence):
            return [
                f"You asked about “{window.unmet}”, which the stored headlines can't isolate. The answer uses the last "
                f"{news_days(window)} days of headlines, so it may not be the period you meant."
            ]
        return []
    oldest = min(newest)
    out = []
    if window.unmet:
        out.append(
            f"You asked about “{window.unmet}”, which the stored daily prices can't isolate. The answer uses the "
            f"{window.label}, up to the close on {oldest}, so it may not be the period you meant."
        )
    for e in prices:  # a window that reaches back past the first stored close is measured from that close
        if e.starts:
            out.append(
                f"The stored daily prices for {e.symbol} start on {e.starts}, so the change is measured from then, not over "
                f"the full {window.label} you asked about."
            )
    if window.asked_day == "today" and oldest != today:
        out.append(f"You asked about today, but the newest stored close is from {oldest}, so the answer is not about today.")
    elif window.asked_day == "yesterday" and oldest != today - timedelta(days=1):
        out.append(f"You asked about yesterday, but the newest stored close is from {oldest}, so the answer may not be about yesterday.")
    return out


def news_days(window: Window) -> int:
    """Headlines default to the last week; a named period is honored up to 90 days."""
    if not window.explicit:
        return 7
    return min(window.days or 90, 90)  # a "since July" window has its own length in `days`
