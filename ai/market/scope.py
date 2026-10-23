"""Questions about something this app does not hold (other assets, untracked companies, names it has never seen) and
requests to write something. The copilot declines these in code, before the model is asked.
"""
import re

import psycopg

# Assets and topics with no data here. Listed by name because a question about one of them with no company in it used to be
# answered from whichever filing mentions it ("What did Bitcoin do this month?" from Tesla's Bitcoin note).
OUTSIDE_ASSET_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|ether|crypto(?:currenc\w+)?|dogecoin|solana|nfts?|gold|silver|platinum|crude(?:\s+oil)?|oil|brent|"
    r"natural\s+gas|copper|wheat|treasur(?:y|ies)|bond\s+yields?|mortgage\s+rates?|interest\s+rates?|inflation|cpi|gdp|recession|"
    r"unemployment|jobs\s+report|the\s+fed|federal\s+reserve|fomc|exchange\s+rates?|forex|the\s+(?:dollar|euro|yen|pound)|"
    r"housing\s+market|central\s+banks?|ecb|bank\s+of\s+(?:england|japan)|rate\s+(?:hikes?|cuts?)|"
    # added 2026-10-17 (fix 5 of the fresh round): fuel and crops, volatility and yields, the economy as a whole, funds and REITs,
    # consumer data, stablecoins, more currencies, politics. Indexes (S&P 500, Dow, Nasdaq) have their own refusal and are not here.
    r"gas(?:oline)?\s+prices?|gasoline|diesel|jet\s+fuel|fuel\s+prices?|at\s+the\s+pump|coffee|corn|soybeans?|sugar|cattle|cotton|"
    r"lumber|cocoa|vix|volatility\s+index|(?:ten|10)[-\s]year\s+(?:yields?|treasur(?:y|ies)|notes?)|"
    r"yields\s+(?:head|go|ris|fall|mov|trend)\w*|where\s+are\s+yields|the\s+economy|(?:the\s+)?stock\s+market|housing\s+bubble|reits?|"
    r"index\s+funds?|etfs?|meme\s+stocks?|student\s+loans?|consumer\s+(?:confidence|sentiment)|retail\s+sales|labou?r\s+market|"
    r"jobs?\s+numbers|payrolls|tether|usdc|stablecoins?|yuan|renminbi|yen|peso|rupee|government\s+shutdown|debt\s+ceiling)\b",
    re.IGNORECASE,
)
# A question that is about what the stored filings say, or compares the tracked companies, is a research question even when
# it mentions Bitcoin or interest rates ("Which of the companies mention interest rate risk?"): never declined.
FILINGS_CUE_RE = re.compile(
    r"\b(?:companies|company|which|mention\w*|disclos\w*|discuss\w*|filings?|10-?[kq]s?|annual\s+reports?|quarterly\s+reports?|"
    r"risk\s+factors?|according\s+to|exposure|exposed|each|every|any\s+of|all\s+of|across)\b",
    re.IGNORECASE,
)
# The same cue for a named company that is not tracked, without the verbs a question applies to that company itself: "Does
# Nintendo disclose anything about piracy?" is a question about Nintendo's filings, not about the stored ones.
COMPANY_CUE_RE = re.compile(
    r"\b(?:companies|company|which|filings?|10-?[kq]s?|annual\s+reports?|quarterly\s+reports?|risk\s+factors?|according\s+to|"
    r"exposure|exposed|each|every|any\s+of|all\s+of|across)\b",
    re.IGNORECASE,
)
# Well-known public companies this app is not tracking. A list, because telling "Intel" from an ordinary capitalised word is
# not something a rule can do; it goes stale, and a company missing from it is simply answered as before (from the filings,
# which say they do not contain it). Ambiguous words (Target, Visa, Ford, Shell, Block, Square) are left out on purpose.
UNTRACKED_COMPANIES = (
    "Meta Platforms", "Facebook", "Netflix", "Intel", "Walmart", "Disney", "Coca-Cola", "PepsiCo", "Nike", "Boeing", "Exxon",
    "ExxonMobil", "Chevron", "JPMorgan", "Goldman Sachs", "Bank of America", "Wells Fargo", "Citigroup", "Mastercard", "Oracle",
    "Salesforce", "Adobe", "IBM", "Cisco", "Qualcomm", "Broadcom", "Uber", "Lyft", "Airbnb", "PayPal", "Starbucks",
    "McDonald's", "Costco", "Home Depot", "Lowe's", "Pfizer", "Moderna", "Johnson & Johnson", "UnitedHealth",
    "Berkshire Hathaway", "Procter & Gamble", "Verizon", "AT&T", "Comcast", "Spotify", "Pinterest", "Shopify", "Palantir",
    "Snowflake", "CrowdStrike", "ServiceNow", "Micron", "Texas Instruments", "Lockheed Martin", "Caterpillar", "Toyota",
    "Honda", "Ferrari", "Rivian", "Lucid", "GameStop", "Robinhood", "Coinbase", "Samsung", "Sony", "Alibaba", "Tencent",
    "Baidu", "ASML", "Zoom",
    # added 2026-10-17 (fix 5 of the fresh round)
    "Chipotle", "Etsy", "Peloton", "Lululemon", "Marriott", "Delta Air Lines", "Delta Airlines", "FedEx", "Eli Lilly", "CVS Health",
    "CVS", "Kroger", "Nintendo", "General Motors", "Taiwan Semiconductor", "Merck", "AbbVie", "UPS", "Dollar General", "Carvana",
    "DoorDash", "Medtronic", "Arm Holdings", "Dell", "Nestle", "Tyson Foods", "Hilton",
    "General Electric", "GE Aerospace", "Honeywell", "Abbott Laboratories", "Amgen", "Gilead", "Bristol Myers", "Regeneron",
    "Novo Nordisk", "Novartis", "Roche", "AstraZeneca", "GlaxoSmithKline", "Sanofi", "Siemens", "Unilever", "Nokia", "Ericsson", "BMW",
    "Volkswagen", "Mercedes-Benz", "Stellantis", "Hyundai", "Nissan", "SoftBank", "Infosys", "HSBC", "Barclays", "Morgan Stanley",
    "BlackRock", "Charles Schwab", "American Express", "Capital One", "Zillow", "eBay", "Wayfair", "Chewy", "Under Armour", "Adidas",
    "Puma", "Kohl's", "Macy's", "Nordstrom", "Best Buy", "Dollar Tree", "Walgreens", "Kraft Heinz", "Mondelez", "General Mills",
    "Hershey", "Reddit", "Roblox", "Unity Software", "Twilio", "Datadog", "Okta", "Atlassian", "Workday", "Intuit", "Autodesk",
    "Zscaler", "Cloudflare", "Fortinet", "Palo Alto Networks", "Arista", "Super Micro", "Western Digital", "Seagate",
    "Applied Materials", "Lam Research", "Marvell", "GlobalFoundries", "Dropbox", "Twitter", "Match Group", "Expedia",
    "Booking Holdings", "Southwest Airlines", "American Airlines", "United Airlines", "JetBlue", "Carnival", "Royal Caribbean",
    "Hertz", "Tata Motors", "Reliance Industries",
)
# also ordinary words (or, for UPS, a plural): need the capital
CAPITALISED_ONLY = {
    "Intel", "Oracle", "Lucid", "Snowflake", "Uber", "Micron", "Cisco", "Sony", "Zoom", "UPS", "Puma", "Intuit", "Workday", "Carnival",
    "Hertz", "Okta", "Arista", "Hilton", "Dell",
}
UNTRACKED_COMPANY_RE = re.compile(
    r"(?<![\w&])(" + "|".join(re.escape(n) for n in sorted(UNTRACKED_COMPANIES, key=len, reverse=True)) + r")(?![\w&])",
    re.IGNORECASE,
)
# Not a research question at all: writing, jokes, recipes, the weather, sports scores.
NOT_RESEARCH_RE = re.compile(
    r"^\W*(?:please\s+)?(?:write|compose|draft|create|generate)\s+(?:me\s+|us\s+)?(?:a|an|some|the)\s+(?:[\w-]+\s+){0,2}"
    r"(?:poem|song|story|joke|essay|haiku|limerick|rap|speech|tweet)\b|"
    r"\btell\s+me\s+(?:a\s+)?(?:joke|story)\b|\b(?:recipes?|weather|who\s+won|final\s+score|horoscope|lyrics)\b",
    re.IGNORECASE,
)


def outside_scope(question: str) -> tuple[str, str] | None:
    """("asset" | "company" | "chat", name) when the question is about something this app does not hold, else None. The
    caller must only use it for a question that names no tracked company: this looks at the words alone."""
    if NOT_RESEARCH_RE.search(question):
        return "chat", ""
    if not COMPANY_CUE_RE.search(question):
        for m in UNTRACKED_COMPANY_RE.finditer(question):
            name = next(n for n in UNTRACKED_COMPANIES if n.lower() == m.group(1).lower())
            if name in CAPITALISED_ONLY and m.group(1) != name:
                continue  # "any intel on the market", "a lucid argument": the word, not the company
            return "company", name
    if FILINGS_CUE_RE.search(question):
        return None
    if OUTSIDE_ASSET_RE.search(question):
        return "asset", ""
    return None


# A request to WRITE something for the reader (an email, a post, a poem, code, slides, a translation), with or without a tracked
# company in it. Declined in code: the app answers questions from stored data, and "Draft an email to my boss about Nvidia's
# results" was answered with a full email built from filing figures. A summary, a list, a table, a comparison, or an overview is
# research and is not here ("Write a summary of Apple's legal proceedings").
_WRITE_VERB = (
    r"(?:write|draft|compose|create|make|generate|prepare|craft|produce|pen|whip\s+up|put\s+together|come\s+up\s+with|"
    r"help\s+me\s+write)"
)
_WRITE_THING = (
    r"(?:e-?mails?|letters?|memos?|messages?|tweets?|captions?|scripts?|slides?|decks?|presentations?|resumes?|cvs?|"
    r"press\s+releases?|newsletters?|toasts?|essays?|speeches|speech|poems?|songs?|haikus?|limericks?|jokes?|raps?|riddles?|"
    # a platform "update" was added after the third sealed round ("Put together a short LinkedIn update on Amazon's quarter." was answered)
    r"(?:linkedin|blog|facebook|instagram|reddit|twitter|social\s+media)\s+(?:posts?|updates?)|blog|thank-?\s?you\s+notes?|notes?\s+to\b)"
)
# Things that are a writing request only after a WRITING verb: "Draft a status update" asks for text, but "Give me a status update on
# Tesla's recall" or "Give me a bio of the CEO" asks for information. "An announcement" counts only when it is for the reader's own
# people: "Did Apple make an announcement?" is research.
_WRITE_ONLY_THING = (
    r"(?:(?:status|team|weekly|monthly|progress)\s+updates?|blurbs?|slogans?|taglines?|jingles?|bios?|"
    r"announcements?(?=\s+(?:for|to)\s+(?:my|our)\b))"
)
# Up to three words between the verb and the thing ("a short poem", "a cover letter"), none of them a preposition: "Write a
# summary of Apple's letter to shareholders" is research.
_BETWEEN = r"(?:(?!of\b|about\b|on\b|from\b|regarding\b|for\b)[\w'’-]+\s+){0,3}?"
WRITING_REQUEST_RE = re.compile(
    rf"\b{_WRITE_VERB}\s+{_BETWEEN}(?:{_WRITE_THING}|{_WRITE_ONLY_THING})\b|"
    rf"\b(?:give|get|show)\s+me\s+(?:a|an|some)\s+{_BETWEEN}{_WRITE_THING}\b|"
    r"\b(?:e-?mail|text|message|dm)\s+(?:my|our|the|a)\s+\w+\s+(?:about|the|that|with)\b|"
    r"\b(?:write|code|build|program|script)\s+(?:me\s+)?(?:a|an|some)\s+(?:[\w-]+\s+){0,3}"
    r"(?:python|javascript|sql|code|function|script|program|macro|bot|query|regex|excel|spreadsheet|formula)\b|"
    r"\btranslate\b|\bsing\s+(?:me\s+|us\s+)?(?:a|an|some)\b",
    re.IGNORECASE,
)


def writing_request(question: str) -> bool:
    return bool(WRITING_REQUEST_RE.search(question))


# A capitalised name in a question that names no tracked company, found nowhere in the stored filings or headlines. A list of
# well-known companies (UNTRACKED_COMPANIES) can never be complete; the stored text is: a name that is not in it cannot be
# answered from it. Words that are capitalised for other reasons are skipped (function words, months and weekdays, acronyms).
_NAME_WORD = r"[A-Z][A-Za-z&'’-]{2,}"
NAME_RUN_RE = re.compile(rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,3}}")
NOT_NAMES = {
    w.lower() for w in (
        "and but for the then also yes please hello thanks what which who whom whose why how when where whether does did has have had "
        "are was were can could would should will may might must not you your yours its they them their this that these those there "
        "here some any all each every both either neither with without about from into than over under after before since until "
        "while okay january february march april june july august september october november december monday tuesday wednesday "
        "thursday friday saturday sunday sec gaap ceo cfo coo cto eps ipo etf etfs fda ftc doj irs nyse nasdaq fed dow usa covid "
        "api esg ttm ytd evs wall street congress treasury federal reserve"
    ).split()
}


def _name_run_words(question: str, run: re.Match) -> list[str]:
    words = [re.sub(r"(?:['’]s|['’])$", "", w) for w in run.group().split()]
    starts_sentence = run.start() == 0 or question[: run.start()].rstrip()[-1:] in ".!?"
    if starts_sentence and not re.search(r"['’]s?$", run.group().split()[0]):
        words = words[1:]  # "What", "Zorblaxx makes what?": a leading capital says nothing, unless it is a possessive
    while words and words[0].lower() in NOT_NAMES:
        words = words[1:]
    while words and words[-1].lower() in NOT_NAMES:
        words = words[:-1]
    return words


def _stored_word(conn: psycopg.Connection, word: str) -> bool:
    """Does this word occur, as a whole word in any case, in a stored filing or headline?"""
    pattern = r"\m" + re.sub(r"([^A-Za-z0-9])", r"\\\1", word) + r"\M"
    return bool(conn.execute(
        "SELECT EXISTS (SELECT 1 FROM filings WHERE text ~* %s) OR EXISTS (SELECT 1 FROM news_articles WHERE title ~* %s)",
        (pattern, pattern),
    ).fetchone()[0])


def unknown_name(conn: psycopg.Connection, question: str) -> str | None:
    """The first capitalised name in the question that appears nowhere in the stored text, or None. The caller must only use
    it for a question that names no tracked company. A filings cue (which companies, a 10-K, exposure...) keeps a question
    about the stored companies answerable, as it does for the other scope rules."""
    if COMPANY_CUE_RE.search(question):
        return None
    for run in NAME_RUN_RE.finditer(question):
        words = _name_run_words(question, run)
        if words and any(not _stored_word(conn, w) for w in words):
            return " ".join(words)
    return None


def join_names(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
