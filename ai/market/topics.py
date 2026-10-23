"""The words and patterns that say what a question is asking about: prices, news, mood, filings, the stored figures,
and the ratios this app does not compute."""
import re
from datetime import date
from functools import lru_cache
from typing import Optional

# A question as it is typed on a phone or in a hurry (DECISIONS: "Typing variants"): a curly apostrophe ("How’s NVDA doing?") and a contraction
# with no apostrophe ("Hows", "Whats", "Wheres", "Whos", "Thats", "Theres") made every rule that looks for "how's" or "what's" miss. Fixed once,
# for the search text only; the question is shown as the owner typed it. "Shows" and "Whatsapp" are not touched (the word must be exactly this).
_CURLY_APOSTROPHES = str.maketrans({"‘": "'", "’": "'"})
_MISSING_APOSTROPHE_RE = re.compile(r"\b(how|what|where|who|that|there)s\b", re.IGNORECASE)


def normalize_typing(text: str) -> str:
    return _MISSING_APOSTROPHE_RE.sub(lambda m: m.group(1) + "'s", text.translate(_CURLY_APOSTROPHES))


PRICE_RE = re.compile(
    r"""\b(?:
        stock\s+price|share\s+price|price\s+(?:history|chart|change|movement|action)|current\s+price|latest\s+price|price\s+today|
        price\s+of|how\s+much\s+(?:is|does|did)|
        (?:stock|shares?)\s+(?:is|are|has|have|was|been|do|does|done|doing|did|up|down|moves?|moved|perform\w*|trad\w+|fell|rose|drop\w*|rall\w+|surg\w+|jump\w*|climb\w*|gain\w*)|
        how(?:'s|\s+is|\s+are)\s+(?:the\s+|its\s+|their\s+)?(?:stock|shares?)\b|
        (?:stock|shares?)\s+(?:go(?:es)?|going|went|gone)\s+(?:up|down|higher|lower|sideways)|
        \w+[-\s](?:day|week|month|year)s?\s+(?:move|movement|swing)s?|(?:daily|weekly|monthly|yearly)\s+(?:move|movement|swing)s?|
        trading|traded|closed|closing|rall(?:y|ied|ies)|surg(?:e|ed|es)|plung\w+|tank(?:ed|s|ing)|(?:will|would|could|might|may|to)\s+tank|sank|fell|fall(?:s|en|ing)?|
        drop(?:s|ped|ping)?|rose|rises?|rising|gain(?:ed|s)?|52[-\s]?week|all[-\s]time\s+(?:high|low)|year[-\s]to[-\s]date|ytd|
        crash\w*|tumbl\w+|soar\w*|slump\w*|spik\w+|skyrocket\w*|sell-?off|rebound\w*|
        volatil\w+|up\s+or\s+down|(?:is|was|are|been)\s+\w+\s+(?:up|down)|(?:up|down)\s+(?:today|this|over|since|in\s+the|for\s+the)|
        how(?:'s|\s+is|\s+are|\s+has|\s+have)\s+.{1,40}?\s+(?:doing|done|going|performing|performed)|
        (?:will|would|could)\s+.{1,40}?\s+(?:go|rise|fall|hit|reach|drop|climb|double)|forecast|predict\w*|price\s+target|
        next\s+(?:week|month|year)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
NEWS_RE = re.compile(
    r"\b(?:news|headlines?|announce\w*|happening|going\s+on|what\s+happened|buzz|chatter|in\s+the\s+press|"
    r"(?:press|media|news)\s+coverage|coverage\s+of|"
    # "stories" only after a word that makes it the news ("customer success stories" is a filings topic)
    r"(?:recent|latest|new|newest|top|breaking|any|some|few|more|other)\s+stories|(?:latest|top|breaking|newest|recent)\s+story)\b",
    re.IGNORECASE,
)
# A news source doing something with the news (third sealed round: "Show me what the papers are printing about Amazon." went to the
# filings, which have no headlines, and the answer said there were none). Structure, not one phrase per wording: the source, then within
# a few words what it does ("the newspapers saying", "columnists write", "the papers have been covering"), or the act "by" / "in" the source
# ("published by the papers", "ran in the papers"). "Papers" counts only as "the papers"; a source with no act ("How many reporters does
# Amazon employ?") and "the press" in "the press release process" are not the news.
_PRESS_VOICE = r"(?:newspapers?|the\s+papers|columnists?|tabloids?|journalists?|reporters?|pundits?|commentators?|bloggers?|the\s+press(?!\s+releases?\b)|the\s+media)"
_PRESS_ACT = (
    r"(?:saying|says?|said|writ(?:ing|es?)|wrote|written|print(?:ing|s|ed)?|publish(?:ing|es|ed)?|report(?:ing|s|ed)?|"
    r"cover(?:ing|s|ed)?|runs?|running|ran)"
)
NEWS_VOICE_RE = re.compile(
    rf"\b{_PRESS_VOICE}\s+(?:[\w'’-]+\s+){{0,3}}?{_PRESS_ACT}\b|\b{_PRESS_ACT}\s+(?:by|in)\s+{_PRESS_VOICE}\b",
    re.IGNORECASE,
)
# "Google doubled this month", "Why did Nvidia triple this year?": a company's stock moving by a multiple or collapsing. Only a
# capitalised company name counts as the subject ("Tesla's deliveries doubled", "revenue doubled" are not), a verb with an object
# is not ("doubled its dividend", "doubled down on", "doubled in size"), and the caller needs a named period or a stock word.
_CLAIM_VERB = (
    r"doubl(?:e|ed|es|ing)|tripl(?:e|ed|es|ing)|quadrupl(?:e|ed|es|ing)|halv(?:e|ed|es|ing)|collaps(?:e|ed|es|ing)|"
    r"plummet(?:ed|s|ing)?|nosedive[sd]?|nosediving|explod(?:e|ed|es|ing)|crater(?:ed|s|ing)?"
)
_NOT_A_COMPANY = (
    r"Revenue|Revenues|Sales|Profit|Profits|Income|Earnings|Dividend|Dividends|Net|Operating|Cash|Free|Margin|Margins|Deliveries|"
    r"Production|Costs|Expenses|Headcount|Employees|Cloud|Data|Services|Segment|Demand|Spending|Debt|Shares|Stock|Price|Prices|AI"
)
PRICE_CLAIM_RE = re.compile(
    rf"(?-i:\b(?!(?:{_NOT_A_COMPANY})\b)[A-Z][\w.&-]*)\s+(?:(?:has|have|had|just|really|actually|also)\s+)*(?:{_CLAIM_VERB})\b"
    r"(?!\s+(?:its|their|the|a|an|his|her|our|my|your|down|in\s+(?:size|number|scale|headcount))\b)",
    re.IGNORECASE,
)
# "Tesla can only go up from here", "Do you think Microsoft reaches $650?": predictions about the price, routed to the prices so the
# prompt's no-prediction rule applies. "reach $100 billion" (a unit) and "revenue to reach" (no capitalised name) are not.
PRICE_PREDICTION_RE = re.compile(
    r"\b(?:can|could|will)\s+only\s+go\s+(?:up|down)\b(?=\s+from\b|\s+forever\b|\W*$)|"
    r"\bonly\s+go(?:es)?\s+(?:up|down)\s+from\s+(?:here|now|this\s+point)\b|"
    r"(?-i:\b[A-Z][\w.&-]*)\s+(?:(?:will|would|could|might)\s+)?reach(?:es)?\s+\$\s?\d[\d,]*+(?:\.\d+)?+"
    r"(?!\s*(?:[bmk]\b|billion|million|trillion|thousand|percent|%))|"
    # "Can you tell me where Apple's stock will be next March?", "Where do you see Nvidia's shares being in the spring?" (fourth sealed round):
    # where the stock will be, with a stock word ("stock-based" does not count)
    r"\bwhere\s+(?:(?:will|would|might|could)\b|do\s+you\s+(?:see|think|expect)\b)[^?.]{0,60}?\b(?:stock|shares?|price)\b(?!-)|"
    r"\b(?:stock|shares?|price)\b(?!-)[^?.]{0,25}?\b(?:will|would|might|could)\s+(?:be|end|trade|close|stand|sit)\b",
    re.IGNORECASE,
)
# "Tell me Apple's close from last Thursday", "Where did Nvidia close yesterday?": the noun or verb "close" as a price. Each form
# needs a day word or a company's possessive, so "Apple's close relationship with TSMC", "close its plant" and "close to a
# deal" stay filings questions.
_WEEKDAY = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
CLOSE_NOUN_RE = re.compile(
    rf"\b[\w.&-]+['’]s\s+close\s+(?:price\s+)?(?:from|on|at|for|in)\s+(?:last|yesterday|today|this|the\s+(?:day|week|month|end)|{_WEEKDAY}|\d)"
    rf"|\bthe\s+close\s+(?:price\s+)?(?:for|on)\s+(?!the\b)[\w.&-]+"
    rf"|\bclose\s+(?:from|on)\s+(?:last|yesterday|{_WEEKDAY})\b"
    r"|\bwhere\s+did\s+[\w.&-]+\s+close\b(?!\s+(?:its|their|the|a|an|down|out|off|to)\b)"
    rf"|\b(?:what\s+)?did\s+[\w.&-]+\s+close\s+(?:at|higher|lower|flat|today|yesterday|on\s+{_WEEKDAY})\b",
    re.IGNORECASE,
)
# A best or worst close ("Give me Nvidia's highest and lowest close of the past quarter.", "Which day did Nvidia close highest?"): the
# noun needs "close" after the extreme, the verb needs the extreme right after it, so "close call", "close partner", "close the highest
# number of stores" and "close its plant" stay filings questions.
_EXTREME = r"(?:high(?:est)?|low(?:est)?|best|worst|top|peak|bottom)"
CLOSE_EXTREME_RE = re.compile(
    rf"\b{_EXTREME}\s+closes?\b(?!\s+(?:call|partners?|relationships?|competitors?|competition)\b)"
    r"|\bclose\s+(?:highest|lowest)\b",
    re.IGNORECASE,
)
# "How big have AMD's swings been over the past quarter?": a company's own swings are the stock's. The name is capitalised and followed
# by 's, so "the swings in Apple's revenue" is not caught, and "swings in" anything but the stock ("Apple's swings in operating expenses")
# is not either.
SWINGS_RE = re.compile(
    r"(?-i:\b[A-Z][\w.&-]*)['’]s\s+(?:[a-z]+\s+)?swings?\b(?!\s+in\s+(?!(?:the\s+)?(?:stock|shares?|price)\b))", re.IGNORECASE
)
# "Where did Nvidia trade this morning?", "Where did AMD settle on Monday?": a company, a verb for where its stock ended up, and a day or part
# of the day. The verb must not take an object ("settle its lawsuit", "open the new store", "finish with the project"), so only the
# stock's own movement is caught.
PRICE_VERB_DAY_RE = re.compile(
    rf"\bwhere\s+did\s+[\w.&-]+\s+(?:trade|settle|finish|open|end|close)\b(?!\s+(?:its|their|the|a|an|with)\b)[^?.]{{0,20}}?"
    rf"\b(?:yesterday|today|this\s+(?:morning|afternoon|week)|(?:on|last)\s+{_WEEKDAY}|overnight)\b",
    re.IGNORECASE,
)
# News with a part of the day, or "come out about" ("Anything interesting come out about Nvidia this morning?" went to the filings and was
# told there are no headlines). A part of the day is a news cue only when the question is not already about prices or the figures.
TIME_OF_DAY_RE = re.compile(r"\b(?:this\s+(?:morning|afternoon|evening)|tonight|overnight|first\s+thing\s+(?:this\s+morning|today))\b", re.IGNORECASE)
COME_OUT_RE = re.compile(r"\b(?:come|comes|came|coming)\s+out\s+(?:about|on|from|for)\b", re.IGNORECASE)
# "How much higher is Nvidia than it was a year ago?", "Is AMD lower than where it was a month ago?": the stock against its
# own past. The subject is one bare name, so "Apple's revenue" and "Tesla's headcount" are not caught; the caller also needs a
# named period and no financial-figure word ("revenue than a year ago" is a figures question).
_BARE_NAME = r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our)\b)[\w.&-]+"
_THAN_THEN = (
    r"than\s+(?:(?:where\s+)?(?:it|they)\s+(?:was|were|stood|sat)\b|"
    r"(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,3})\s+(?:day|week|month|year)s?\s+ago\b)"
)
PERIOD_COMPARE_RE = re.compile(
    rf"\bhow\s+much\s+(?:higher|lower|more|less)\s+(?:is|are|was)\s+{_BARE_NAME}\s+(?:now\s+)?{_THAN_THEN}"
    rf"|\b(?:is|are|was|were)\s+{_BARE_NAME}\s+(?:now\s+)?(?:higher|lower|above|below)\s+{_THAN_THEN}",
    re.IGNORECASE,
)
# A company and its stock with nothing else in the question ("What about Tesla's stock?", "Tesla stock?"). It has no verb,
# so PRICE_RE misses it and it went to the filings (the answer was Tesla's headcount and lawsuits). Deliberately narrow:
# only filler words may come before the one name-like word, and nothing but a time word ("now", "please") may follow
# "stock", so "Should I buy Tesla stock?", "Tesla's stock-based compensation" and "What does Tesla say about its stock?"
# are not caught.
BARE_STOCK_RE = re.compile(
    r"^\W*(?:(?:and|or|so|ok|okay|then|also|now|what|how|about|what's|whats|how's|hows)[\s,]+)*"
    r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our|what|which|who|why|how|any|some|each|every|no|"
    r"penny|growth|value|tech|cheap)\b)[\w.&-]+(?:['’]s)?\s+(?:stocks?|shares?)"
    r"(?:[\s,]+(?:now|currently|right now|today|please|then|too|again|as well|at the moment|lately))*\W*$",
    re.IGNORECASE,
)
# "Show me how Alphabet has moved over the last three months": a company, a movement verb, and (checked separately, with
# parse_window) a named period. No "stock" or "shares" is needed. The subject must be one bare name, so "Apple's headcount
# moved" is not caught, and the verb must not take an object ("move its supply chain", "move into cloud").
PERIOD_MOVE_RE = re.compile(
    r"\bhow\s+(?:(?:has|have|had|did|does|do)\s+)?"
    r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our|much|many)\b)[\w.&-]+\s+(?:(?:has|have|had)\s+)?"
    r"(?:moved?|trended|fared|swung|swing)\b(?!\s+(?:its|their|the|a|an|to|into|from|out|on|up\s+to|toward\w*)\b)"
    r"|\bwhere\s+(?:has|have|had|did)\s+(?!(?:the|its|their|this|that)\b)[\w.&-]+\s+(?:moved?|trended|fared|swung)\b"
    r"(?!\s+(?:its|their|the|a|an|to|into|from|out|on)\b)",
    re.IGNORECASE,
)
# "Has Apple been climbing or sliding lately?", "Is Amazon's share value holding steady lately?": a company (or its stock, shares, share
# or stock value, quote), a word for how a price is moving, and (checked in `detect_intent`) a recency word or a named period. No "stock"
# or price verb is needed. The movement word must be followed by nothing, a direction or a joiner, never an object, so "climbing the
# ranks", "slipping on iPhone sales", "sliding into", "drifting from its mission" and "sinking money into AI" are not caught; "Microsoft's
# market share sliding" is not either (the possessive may only name the stock). The subject is not a figure ("Is revenue climbing lately
# for Tesla?"): `_NOT_A_COMPANY`, as in the claim rule. "up" and "down" are not listed: "been sliding down" is a price question already.
_MOVING = r"(?:climbing|sliding|slipping|drifting|sagging|trending|sinking|dipping|holding\s+(?:steady|firm|flat))"
RECENT_MOVE_RE = re.compile(
    rf"\b(?:has|is|was|were)\s+(?!(?:{_NOT_A_COMPANY})\b){_BARE_NAME}(?:['’]s\s+(?:stock|shares?|share\s+value|stock\s+value|quote))?\s+(?:been\s+)?"
    rf"{_MOVING}\b(?=\s*[?,]|\s*$|\s+(?:higher|lower|sideways|again|steadily|slowly|a\s+bit|or|and|lately|recently|these|of|this|over|since|today)\b)",
    re.IGNORECASE,
)
RECENCY_RE = re.compile(r"\b(?:lately|recently|these\s+days|of\s+late)\b", re.IGNORECASE)
LATELY_RE = re.compile(r"\blately\b", re.IGNORECASE)  # a news cue ("What are people saying about Microsoft lately?") unless it is a price question


@lru_cache(maxsize=4)
def _year_start_re(year: int) -> re.Pattern:
    """"Is Amazon above where it started 2026?": a comparison with where the stock stood at the start of THIS year. Only the
    current year (or "the year", "last year"'s close) is accepted, because the year-to-date window is wrong for any other."""
    return re.compile(
        r"\bwhere\s+(?:it|they|the\s+stock|the\s+shares)\s+(?:"
        rf"(?:started|began|opened|stood|was|were|sat)\s+(?:the\s+year|(?:in\s+)?{year}|at\s+the\s+(?:start|beginning)\s+of\s+(?:the\s+year|{year}))|"
        r"(?:finished|ended|closed)\s+last\s+year)\b",  # not "was last year": that can be anything, such as revenue
        re.IGNORECASE,
    )


@lru_cache(maxsize=4)
def _when_year_opened_re(year: int) -> re.Pattern:
    """"Is Amazon's share price higher than when the year opened?", "Is Tesla up on where it was when 2026 began?": the same
    comparison, worded with "when". The caller also needs the stock or a bare company name as the subject, because
    "Was Tesla's headcount larger than when the year began?" is not about the price."""
    return re.compile(
        r"\b(?:than|on|from|above|below|ahead\s+of|behind|compared\s+(?:with|to)|versus|vs\.?|relative\s+to|against)\s+"
        r"(?:where\s+(?:it|they)\s+(?:was|were)\s+)?"
        rf"when\s+(?:the\s+year|{year})\s+(?:opened|began|started|kicked\s+off)\b",
        re.IGNORECASE,
    )


_BARE_PRICE_SUBJECT_RE = re.compile(rf"\b(?:is|are|was|were|has|have)\s+{_BARE_NAME}\s+(?:up|down|higher|lower|above|below|ahead|behind)\b", re.IGNORECASE)


def year_start_comparison(question: str, today: Optional[date] = None) -> bool:
    year = (today or date.today()).year
    if _year_start_re(year).search(question):
        return True
    return bool(_when_year_opened_re(year).search(question)) and bool(
        STOCK_WORD_RE.search(question) or _BARE_PRICE_SUBJECT_RE.search(question))


GENERAL_RE = re.compile(r"\bhow(?:'s|\s+is|\s+are|\s+has|\s+have)\s+.{1,40}?\s+(?:doing|done|going|performing|performed)\b", re.IGNORECASE)
STOCK_WORD_RE = re.compile(r"\b(?:stocks?|shares?|prices?)\b", re.IGNORECASE)
# "How much did Apple earn / pay in dividends / bring in?" begins like a price question ("how much did") but asks what the
# company did with money. Cut out only when the same question has a money verb or noun after it and no stock word anywhere
# (the caller checks that), so "How much did Apple stock lose?" is still a price question.
HOW_MUCH_MONEY_RE = re.compile(
    r"\bhow\s+much\s+(?:money\s+|cash\s+)?(?:did|does|is|has|have)\b(?=[^?.]{0,80}\b(?:earn\w*|mak(?:e|es|ing)|made|net(?:ted)?|"
    r"pa(?:y|id|ys)|spen[dt]\w*|sell\w*|sold|bring\w*|brought|rais(?:e|es|ed|ing)|generat\w*|report\w*|borrow\w*|owe\w*|profit\w*|"
    r"revenues?|sales|income|dividends?|cash)\b)",
    re.IGNORECASE,
)
# No index data is stored, and a filing's "total return" chart (scaled from $100) reads like an index level to a model.
INDEX_RE = re.compile(r"\b(?:s&p(?:\s*500)?|dow(?:\s+jones)?|nasdaq(?:\s+composite)?|russell\s*\d+)\b", re.IGNORECASE)
STOCK_NOUN_RE = re.compile(r"\b(?:stocks?(?!-based)|shares)\b", re.IGNORECASE)  # not "stock-based compensation"
_NEWS_SOURCE = r"reporters?|journalists?|press|media|coverage|headlines?|news(?:\s+flow)?|writers?|commentators?|pundits?|buzz|chatter"
_NEWS_TONE = (
    r"kind|harsh|friendly|hostile|fa?vou?rabl[ey]|unfa?vou?rabl[ey]|nice|piling\s+on|bashing|trashing|slamming|praising|"
    r"treating|upbeat|gloomy|supportive|critical|flattering|rosy|grim|optimistic|pessimistic|warm|cold|gentle|brutal|glowing|"
    r"scathing|good|bad|better|worse|improving|souring|warming|"
    r"turned\s+on|turning\s+on|easy\s+ride|rough\s+ride|hard\s+time|free\s+pass|going\s+(?:easy|hard)\s+on"
)
SENTIMENT_RE = re.compile(
    r"\b(?:sentiment|mood|bullish|bearish|optimis\w+|pessimis\w+|tone\s+of|(?:good|bad|positive|negative)\s+news|"
    r"how\s+(?:do|does|are)\s+(?:people|investors|the\s+market|reporters|journalists|the\s+press|the\s+media|commentators)\s+"
    r"(?:feel|think|see|view)|"
    r"\b(?:media|press|news|coverage)\b[^?.]{0,25}\b(?:tone|mood|vibe)\b|\b(?:tone|mood|vibe)\b[^?.]{0,25}\b(?:media|press|news|coverage)\b|"
    r"\bvibes?\b|\bsour(?:ing|ed)?\s+on\b|"
    r"\b(?:turn\w*|get\w*|grow\w*|becom\w*)\s+(?:more\s+)?(?:sour|bullish|bearish)\b|"  # not "negative": cash flow can turn negative
    r"\b(?:press|media|coverage|reporters|journalists)\b[^?.]{0,30}\b(?:negative|positive)\b|"
    r"\bcoverage\b[^?.]{0,30}\b(?:trend\w*|shift\w*|chang\w*|improv\w*|worsen\w*|deteriorat\w*)\b|"
    r"feel(?:ing|s)?\s+(?:positive|negative|good|bad)|investors?\s+(?:feel|are\s+feeling|think)|what\s+do\s+investors|"
    r"how\s+(?:negative|positive)\b|"
    # a news source near a word about its attitude, either order ("are reporters being kind or harsh", "headlines mostly good"):
    # structure, not one phrase per wording. Analysts are not a news source here ("do analysts expect positive growth").
    rf"\b(?:{_NEWS_SOURCE})\b[^?.]{{0,40}}\b(?:{_NEWS_TONE})\b|\b(?:{_NEWS_TONE})\b[^?.]{{0,40}}\b(?:{_NEWS_SOURCE})\b|"
    # stories, headlines or articles that are "mostly positive", "more negative than positive", "lean positive or negative"
    # (plural only, so "headline earnings" is not one; a bare "negative" is not enough, since a list of bad stories is not a score)
    r"\b(?:stories|headlines|articles|news|coverage)\b[^?.]{0,40}\b(?:(?:more|mostly|mainly|largely|predominantly)\s+(?:positive|negative)|"
    r"positive\s+(?:or|vs\.?|versus|than)\s+negative|negative\s+(?:or|vs\.?|versus|than)\s+positive|"
    r"(?:lean\w*|tilt\w*|skew\w*)\s+(?:positive|negative))\b|"
    r"\b(?:saying|said|writing|written)\s+(?:nice|good|bad|kind|mean|positive|negative)\s+things\s+about\b|"
    r"\b(?:feeling|feelings|attitude|stance|take)\s+(?:about|on|toward|towards)\b[^?.]{0,50}\b(?:news|press|media|coverage|headlines)\b)",
    re.IGNORECASE,
)
# A question that asks what moved the price. On a price question it brings the headlines too (published beside the move, never offered as
# its cause). "What drove it?", "What caused ...", "What triggered ...", "How come ...", "What's responsible for ..." count as well as "why".
CAUSE_RE = re.compile(
    r"\b(?:why|reasons?|because|what\s+happened|what(?:'s|\s+is|\s+was)\s+(?:behind|driving|causing|moving)|"
    r"what\s+(?:drove|caused|triggered|sparked|prompted|pushed|made|led\s+to|explains?|explained)|how\s+come|"
    r"what(?:'s|\s+is|\s+was)\s+(?:responsible\s+for|the\s+(?:story|cause|reason)\s+(?:behind|of|for))|"
    r"(?:drove|caused|triggered|sparked|prompted)\s+(?:it|that|this|the\s+(?:move|drop|jump|rise|fall|surge|plunge|rally|selloff|slide|spike)))\b",
    re.IGNORECASE,
)
# The move named as a noun: "Amazon's jump this month", "Nvidia's slide", "the move in Microsoft stock". With a cause word these are price
# questions even without a price verb or the word "stock". Only the nouns that no price rule knew ("jump", "slide", "swoon") are named here:
# "drop", "rally", "surge", "crash" were price words already. "Nvidia's slide in gross margin" is a business metric, not the stock.
PRICE_MOVE_NOUN_RE = re.compile(
    r"(?-i:\b[A-Z][\w.&-]*)['’]s\s+(?:jump|slide|swoon)\b(?!\s+in\s+(?!stock\b|shares?\b|price\b))|"
    r"\b(?:move|moves|jump|slide|swoon|selloff|sell-off|plunge|rally|surge)\s+in\s+(?-i:[A-Z][\w.&-]*)\s+(?:stock|shares?)\b",
    re.IGNORECASE,
)
FILING_RE = re.compile(
    r"\b(?:filings?|10-?k|10-?q|annual\s+report|quarterly\s+report|sec|risks?|risk\s+factors|legal|litigation|lawsuits?|"
    r"competition|competitors?|employees|headcount|revenues?|income|profits?|margins?|segments?|strategy|business|"
    r"operations|supply\s+chain|regulat\w+|cash|debt|liabilit\w+|guidance|capex|capital\s+expenditures?)\b",
    re.IGNORECASE,
)


# Company financial figures (P/E, market value, revenue, profit, margins) from the stored SEC figures.
# Specific wording first. Every match is cut out of the question before the next pattern runs, so "price-to-earnings"
# counts once as a P/E question and not again as an "earnings" (profit) one.
# A company named as the subject of "worth" or "valued at": one or two words with no possessive ("Microsoft", "Apple Inc",
# "all of Tesla"), so "Microsoft's goodwill", "the inventory" and "its patents" are not a company's total value.
_SUBJ = r"(?:all\s+of\s+)?(?!(?:the|its|their|a|an|this|that|these|those|my|your|our)\b)[\w.&-]+(?:\s+(?:inc|corp|corporation|company|co)\b\.?)?"
MARKET_VALUE_PATTERN = (
    r"\bmarket[-\s]cap(?:italization|italisation)?\b|\bmarket\s+(?:value|valuation)\b|"
    rf"\b(?:what(?:'s|\s+is|\s+are)|how\s+much\s+(?:is|are))\s+{_SUBJ}\s+worth\b(?!\s+(?:buying|selling|investing|holding|owning|it\b|the\b|a\b|an\b|to\b))|"
    rf"\bwhat(?:'s|\s+is|\s+was)\s+{_SUBJ}\s+valued\s+at\b|"
    r"\b(?:total|combined|overall|aggregate)\s+value\s+of\s+(?:all\s+of\s+)?[\w.&'’ -]{0,30}?\b(?:shares|stock|equity)\b|"
    r"\bcompany['’]?s?\s+value\b|\bcost\s+to\s+(?:buy|purchase|acquire)\s+(?:all\s+of|the\s+(?:whole|entire))\b|"
    # a company's total value worded around its shares (third sealed round: "How big is Apple, in terms of what all its shares are
    # worth?" went to the prices and was told market value is not available)
    r"\ball\s+(?:of\s+)?(?:its|their|[\w.&-]+['’]s)\s+shares\s+(?:(?:are\s+)?worth|add\s+up\s+to)\b|"
    r"\b(?:combined|total|overall|aggregate|collective)\s+(?:worth|value)\s+of\s+(?:all|every|each)\s+(?:of\s+)?(?:the\s+)?"
    r"(?:[\w.&'’-]+\s+){1,2}?(?:shares?|stock)\b|"
    r"\bhow\s+much\s+(?:is|are)\s+(?:the\s+)?(?:whole|entire)\s+(?:of\s+)?(?:[\w.&-]+\s+){0,2}?worth\b|"
    r"\badd(?:ed|ing)?\s+up\s+(?:all|every|each)\s+(?:of\s+)?(?:the\s+)?(?:[\w.&'’-]+\s+){0,2}?shares?\b"
)
_SPECIFIC_TOPICS = (
    ("pe", r"\bp\s?/\s?e\b|\bpe\s+(?:ratio|multiple)\b|\bprice[-\s]to[-\s]earnings\b|\bearnings\s+multiple\b"),
    ("market_value", MARKET_VALUE_PATTERN),
    ("eps", r"\beps\b|\bearnings\s+per\s+share\b"),
    ("shares", r"\bshares\s+outstanding\b|\bshare\s+count\b|\bnumber\s+of\s+shares\b"),
)
# Everyday words that a filing can also answer. Left to the filings when the question names a filing, a quarter, a
# segment, or asks why (the figures are twelve-month totals and can't explain anything).
_NOT_SALES_SIDE = (  # words after "sales" that make it a department, a tax, or a cost, not the company's revenue
    r"(?!\s+(?:tax|taxes|team|teams|force|staff|office|offices|people|reps?|channels?|practices|cycle|organi[sz]ation|"
    r"pipeline|commissions?|and\s+marketing|general|costs?|expenses?)\b)"
)
_BROAD_TOPICS = (
    # "earn" counts only as the company's own: "How much did Amazon earn", "What did Microsoft earn" (one bare name as the
    # subject), so "How much do Apple engineers earn?" is left alone
    ("profit", r"\bnet\s+income\b|\bprofit(?:s|ability|able)?\b|\bearnings\b|\boperating\s+income\b|\bbottom\s+line\b|"
               r"\b(?:what|how\s+much(?:\s+money)?)\s+(?:did|does|do|has|have|had|will|would)\s+"
               r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our)\b)[\w.&-]+\s+earn(?:ed)?\b|"
               # what a company "clears" or "pockets" after its costs (fourth sealed round: "What did Tesla clear after all expenses?")
               r"\b(?:clears?|cleared|nets?|netted|pocket(?:s|ed)?|(?:take|takes|took)\s+home)\b[^?.]{0,25}?"
               r"\bafter\s+(?:all\s+)?(?:(?:its|their|the)\s+)?(?:expenses|costs|taxes|everything)\b"),
    # "Of every sales dollar, how much does Apple keep after paying for production?" (fourth sealed round): a keeping word after "every /
    # each dollar" is a margin question however the costs are worded
    ("margin", r"\bmargins?\b|\b(?:every|each)\s+(?:sales\s+|revenue\s+)?dollar\b[^?.]{0,80}?"
               r"\b(?:keeps?|kept|left|remain(?:s|ing)?|retain(?:s|ed)?|pocket(?:s|ed)?|stays?|hold(?:s)?\s+on(?:to|\s+to))\b"),
    # "sales" counts as the company's revenue only in the forms that cannot mean a product or a department: "Nvidia's sales",
    # "total / net sales", "dollars of sales". Not "iPhone sales (over the past year)", "retail sales", "sales tax" or "the
    # sales team" (a "sales over the last ..." form was tried and dropped: it caught "iPhone sales over the past year").
    # Money coming in ("how much money did Tesla bring in") is revenue too.
    ("revenue", r"\brevenues?\b|\btop\s+line\b|"
                rf"\b(?:total|net|overall|combined|annual|yearly|its|their|[\w.&-]+['’]s)\s+sales\b{_NOT_SALES_SIDE}|"
                r"\b(?:dollars|amount|value)\s+of\s+sales\b|"
                r"\bhow\s+(?:much|many)\s+(?:money|cash|dollars)\b[^?.]{0,50}?\b(?:bring|brought|brings|take|took|pull|pulled)\s+in\b"),
    ("general", r"\bfinancials?\b|\bfundamentals?\b|\bvaluation\b|\bfinancial\s+(?:figures|results|health|position|summary)\b"),
)
FILING_FORM_RE = re.compile(
    r"\b(?:10-?k|10-?q|8-?k|filings?|annual|quarter(?:s|ly)?|fiscal|segments?|earnings\s+(?:call|release|report)|"
    r"by\s+(?:product|region|geograph\w+|business|division))\b",
    re.IGNORECASE,
)
# "The last four quarters" is the twelve months the stored figures cover, not a request for one quarter's filing; "last
# quarter" and "the second quarter" still are.
TWELVE_MONTHS_AS_QUARTERS_RE = re.compile(
    r"\b(?:last|past|previous|trailing|prior|latest|recent)\s+(?:4|four)\s+quarters\b", re.IGNORECASE
)
WHY_RE = re.compile(
    r"\b(?:why|reasons?|because|explain\w*|what\s+(?:happened|drove|drives|caused|causes)|driv(?:e|es|ing|en|ers?)|"
    r"caus(?:e|es|ed|ing)|what(?:'s|\s+is|\s+was)\s+behind)\b",
    re.IGNORECASE,
)


# "How many shares does Apple have?" asks for the stored share count. The price rules used to read "shares does" as a
# price verb and answer it from price data, which has no share count. A question about what was done with shares
# (repurchased, issued, owned, sold, can I buy) is a filings question: the phrase is still cut out so it isn't read as a
# price question, but no figure is asked for.
HOW_MANY_SHARES_RE = re.compile(r"\bhow\s+many\s+(?:[\w.&'’-]+\s+){0,2}?shares\b", re.IGNORECASE)  # "how many Nvidia shares"
SHARES_ACTION_RE = re.compile(
    r"\b(?:repurchas\w*|buy\s?backs?|bought|buy|buying|issu\w*|sold|sell|selling|trad\w*|split\w*|own\w*|held|hold|"
    r"granted|vest\w*|award\w*|short|dividends?)\b",
    re.IGNORECASE,
)


def _topics(text: str, patterns) -> tuple[set[str], str]:
    found, rest = set(), text
    for topic, pattern in patterns:
        if re.search(pattern, rest, re.IGNORECASE):
            found.add(topic)
            rest = re.sub(pattern, " ", rest, flags=re.IGNORECASE)
    return found, rest


def figure_topics(text: str) -> frozenset[str]:
    """Which financial figures a piece of text is about. Used on a question and on an answer, with no exceptions."""
    specific, rest = _topics(text, _SPECIFIC_TOPICS)
    broad, _ = _topics(rest, _BROAD_TOPICS)
    return frozenset(specific | broad)


def question_topics(question: str) -> tuple[frozenset[str], str]:
    """The financial figures a question asks for, and the question with those words cut out (so they don't also send it
    to the filings). Everyday words are left to the filings when the question is plainly about a filing or asks why."""
    specific, rest = _topics(question, _SPECIFIC_TOPICS)
    broad, rest_without_broad = _topics(rest, _BROAD_TOPICS)
    if broad and (FILING_FORM_RE.search(TWELVE_MONTHS_AS_QUARTERS_RE.sub(" ", question)) or WHY_RE.search(question)):
        return frozenset(specific), rest  # the everyday words stay in the question, for the filings rules to see
    return frozenset(specific | broad), rest_without_broad


# Well-known ratios this app does not compute. Only the explicit names are listed (a bare "book value" or "dividends"
# can be a plain filings question). Asked for one of these, the copilot says it doesn't calculate it, in code, because
# the model only saw filing text, found no price, and said "the stock price is not provided" although prices are stored.
_UNSTORED = (
    ("dividend yield", r"\bdividend\s+yield\b"),
    ("price-to-book ratio", r"\bprice[-\s]to[-\s]book\b|\bp\s?/\s?b\b|\bpb\s+ratio\b"),
    ("price-to-sales ratio", r"\bprice[-\s]to[-\s]sales\b|\bp\s?/\s?s\b|\bps\s+ratio\b"),
    ("PEG ratio", r"\bpeg(?:\s+ratio)?\b"),
    ("EV/EBITDA", r"\bev\s?/\s?ebitda\b"),
    ("EV/sales", r"\bev\s?/\s?(?:sales|revenue)\b"),
    ("price-to-free-cash-flow ratio",
     r"\bprice[-\s]to[-\s](?:free[-\s]cash[-\s]flow|fcf)\b|\bp\s?/\s?fcf\b|\bpfcf\b"),
    ("price-to-cash-flow ratio", r"\bprice[-\s]to[-\s]cash[-\s]flow\b|\bp\s?/\s?cf\b"),
    ("free cash flow yield", r"\b(?:free[-\s]cash[-\s]flow|fcf)\s+yield\b"),
    ("earnings yield", r"\bearnings\s+yield\b"),
    ("current ratio", r"\bcurrent\s+ratio\b"),
    ("quick ratio", r"\b(?:quick|acid[-\s]test)\s+ratio\b"),
    ("return on invested capital", r"\broic\b|\breturn\s+on\s+(?:invested\s+)?capital\b"),
    ("interest coverage ratio", r"\binterest\s+coverage(?:\s+ratio)?\b"),
    ("enterprise value", r"\benterprise\s+value\b"),
    ("return on equity", r"\breturn\s+on\s+equity\b|\broe\b"),
    ("return on assets", r"\breturn\s+on\s+assets\b|\broa\b"),
    ("debt-to-equity ratio", r"\bdebt[-\s]to[-\s]equity\b"),
)


def unstored_figures(question: str) -> tuple[tuple[str, ...], str]:
    """The ratios the question asks for that aren't computed here, and the question with those words cut out (so
    "price-to-book" isn't also read as a price question)."""
    found, rest = [], question
    for name, pattern in _UNSTORED:
        if re.search(pattern, rest, re.IGNORECASE):
            found.append(name)
            rest = re.sub(pattern, " ", rest, flags=re.IGNORECASE)
    return tuple(found), rest
