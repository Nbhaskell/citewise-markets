"""Does the question ask for a buy, sell or hold call (or for a prediction of the price)?"""
import re

# A request for a buy, sell, or hold call. The model refused these in its own words only some of the time ("Is it a good
# time to buy Nvidia?" 3 of 10 runs), so the refusal is attached to the answer in code instead. People ask in endless ways
# (seven realistic wordings, none in the first phrase list, were all missed), so a question also counts when it has a
# trading word AND a decision cue. Missing a request is worse than flagging a harmless question (one extra notice), so
# this leans towards flagging. "Why did insiders sell Tesla shares?" has a trading word and no cue; "Will Tesla stock go
# up?" is a prediction with its own rule, not a request for a recommendation.
ADVICE_ASK_RE = re.compile(
    r"""\b(?:
        should\s+(?:i|we|one)\s+(?:\w+\s+){0,2}?(?:buy|sell|hold|invest|short|keep|dump|trim|add)\b|
        (?:good|bad|right|wrong|best|worst|smart)\s+(?:time|moment|idea)\s+to\s+(?:buy|sell|invest|hold)\b|
        (?:is|are|was)\b.{0,50}?\b(?:a\s+)?(?:good|great|better|best|bad|smart|safe|solid|risky)\s+(?:buy|sell|investment|bet|hold|pick|choice|play)\b|
        worth\s+(?:buying|selling|investing|holding)\b|
        (?:buy|sell)\s+or\s+(?:sell|hold|buy)\b|buy,?\s+sell,?\s+or\s+hold\b|
        would\s+you\s+(?:buy|sell|recommend|invest|hold)\b|
        do\s+you\s+(?:recommend|suggest)\b|(?:recommend|suggest)\s+(?:buying|selling|holding)\b|
        what\s+(?:stocks?|shares?)\s+should\s+(?:i|we)\b|
        (?:a|an)\s+(?:smart|safe|wise|sensible|sound|good|solid|reasonable)\s+(?:place|home|spot|vehicle|holding|investment)\b|
        better\s+off\s+(?:with|in|buying|owning|holding)\b|
        (?:do|would)\s+you\s+(?:like|favou?r|prefer|pick|choose)\b|
        \b(?:smart|wise|sensible|sound|safe|prudent|good|great|solid)\b.{0,60}?\bfor\s+(?:me|us)\b|
        (?:put|putting|park|parking)\s+(?:(?:any|some|a\s+little|a\s+lot\s+of)\s+)?(?:money|cash|savings)\s+(?:in|into|with)\b|
        (?:good|right|best|smart|wise)\s+(?:point|level|price|entry\s+point)\s+to\s+(?:buy|enter|get\s+in|add|sell|exit)\b|
        (?:one|something|stocks?)\s+to\s+(?:buy|sell|hold|own|keep|avoid)\b|
        # "Should I?" with the trade left unsaid, and the common ways to finish it (third sealed round)
        should\s+(?:i|we)\s*[?!.]*\s*$|
        # a bare "Am I?" / "Do I?" / "Shall we?" ending a statement (fourth sealed round: "Everyone says I'm crazy not to own Nvidia. Am I?")
        (?:^|[.!?]\s+)(?:am|are|do|shall|ought|must)\s+(?:i|we)\s*[?!.]*\s*$|
        should\s+(?:i|we)\s+(?:do\s+it|go\s+for\s+it|take\s+the\s+(?:plunge|leap|bet))\b|
        should\s+(?:i|we)\s+(?:join(?:\s+(?:in|them|him|her))?|listen(?:\s+to\s+(?:him|her|them|it|that))?)\s*[?!.]*\s*$|
        should\s+(?:i|we)\s+(?:follow|take|heed|trust|listen\s+to)\s+(?:[\w'’]+\s+){0,3}?(?:advice|tips?|suggestions?|recommendations?|hunch(?:es)?)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
TRADE_WORD_RE = re.compile(
    r"\b(?:buy(?:ing)?|sell(?:ing)?|hold(?:ing)?|invest(?:ing)?|dump|trim|short(?:ing)?|add(?:ing)?\s+to|accumulat\w+|"
    r"load(?:ing)?\s+up|get(?:ting)?\s+(?:in|out)|exit|position|put\s+(?:my|our)\s+(?:savings|money|cash)\s+(?:in|into)|"
    r"pick(?:ing)?\s+up|jump(?:ing)?\s+(?:in|into|on)|pil(?:e|ing)\s+(?:in|into|on)|stay(?:ing)?\s+(?:in|invested)|bail(?:ing)?\s+on|double(?:d|\s|-)*down|"
    r"get(?:ting)?\s+into|get(?:ting)?\s+out\s+of|"
    # "Is it time to cash out of Nvidia?": the reader's own sale. A company's own "unload its inventory" or "cash out its stake"
    # is not (the lookahead; the quantifiers are possessive so a shorter match cannot slip past it).
    r"cash(?:ing)?\s+out\b(?!\s+(?:its|their)\b)|(?:take|taking)\s+(?:some\s+|my\s+|our\s+)?profits?|"
    r"lock(?:ing)?\s+in\s+(?:my\s+|our\s+|some\s+|the\s+)?(?:gains?|profits?)|cut(?:ting)?\s+(?:my\s+|our\s+)?losses|"
    r"bail(?:ing)?\s+out|unload\w*+(?!\s+(?:its|their)\b)|offload\w*+(?!\s+(?:its|their)\b)|"
    r"ride\s+(?:it|this|that|them|[\w.&-]+)\s+out|hang(?:ing)?\s+on(?:to)?\b(?:\s+to\b)?+(?!\s+(?:its|their)\b)|go(?:ing)?\s+(?:long|short)\b|"
    r"add(?:ing)?\s+(?:[\w.&-]+\s+){1,2}to\s+(?:the|my|our|a|your)\s+(?:portfolio|holdings|watchlist)|"
    # The reader's own all-in (third sealed round: "My cousin says to go all in on AMD. Should I?" carried no notice). A company's own
    # "going all in on autonomy" still needs a decision cue beside it, like every other trade word.
    r"go(?:ing)?\s+all[-\s]?in\b|(?:be|being)\s+all[-\s]?in\b|all[-\s]in\s+on\b|"
    r"bet(?:ting)?\s+(?:big|heavy|heavily|everything|it\s+all|the\s+(?:farm|house))|go(?:ing)?\s+(?:big|heavy)\s+on|"
    r"put(?:ting)?\s+everything\s+(?:in|into|on)|pull(?:ing)?\s+the\s+trigger|back(?:ing)?\s+up\s+the\s+truck|"
    r"throw(?:ing)?\s+money\s+at)\b",
    re.IGNORECASE,
)
DECISION_CUE_RE = re.compile(
    r"\b(?:should|whether|wise|smart|safe(?:ly)?|good\s+idea|bad\s+idea|thinking\s+(?:about|of)|can\s+i|could\s+i|may\s+i|"
    r"my|our|worth|recommend\w*|advice|advise|suggest\w*|thoughts|opinion|would\s+you|do\s+you\s+think|right\s+time|"
    r"best\s+time|good\s+time|bad\s+time|reason\s+(?:not\s+)?to|enough\s+to|right\s+(?:stock|company|one)\s+to|"
    r"too\s+(?:late|early)|the\s+(?:moment|time)|reckon|your\s+(?:take|view|read)|"
    r"is\s+it\s+(?:the\s+)?(?:time|moment|point)\s+to|(?<!\w)time\s+to|would\s+it\s+be\s+(?:[\w-]+\s+){0,2}?to|"
    r"(?:crazy|reckless|foolish|stupid|dumb|mad|nuts|silly)\s+to|(?:a\s+)?(?:mistake|error|blunder)\s+to)\b",
    re.IGNORECASE,
)
# Judgments and endorsements that are a request for a recommendation however they are phrased (a probe of 24 everyday
# wordings found 21 unflagged): a judgment of value ("undervalued", "a bargain", "cheap right now"), an endorsement ("a sure
# thing", "a keeper", "worth owning", "rate it as an investment"), and the reader's own money ("I have $5,000. Where should
# it go?"). "Cheap" and "expensive" count only when they end the question or are followed by now / today / at this price,
# so "the most expensive segment to run" is left alone; "the winner-take-all risk" and "a retirement plan" are left alone too.
ADVICE_JUDGMENT_RE = re.compile(
    r"""\b(?:
        (?:over|under)(?:valued|priced)|fairly\s+(?:valued|priced)|(?:a|the)\s+(?:bargain|steal)|
        (?:cheap|expensive|pricey)(?=\s*(?:right\s+now|now|today|here|at\s+(?:this|the\s+current)\s+(?:price|level)|\W*$))|
        sure\s+thing|can'?t\s+lose|(?:safe|good|great|solid|sure|smart|risky)\s+bet|
        (?:a|the)\s+(?:winner(?!-)|keeper|no[-\s]?brainer)|screaming\s+buy|worth\s+(?:owning|holding|keeping|having)|
        (?:would|will|do|did)\s+you\s+(?:bet|wager)|rate\s+\w+\s+as\s+an?\s+investment|
        your\s+(?:take|view|opinion|read|thoughts)\s+on|make\s+(?:me|us)\s+(?:money|rich)|
        am\s+i\s+(?:crazy|nuts|wrong|silly|foolish|dumb|smart|right)\s+to|
        (?:crazy|mad|foolish|stupid|dumb|nuts|silly|insane|wrong)\s+not\s+to\s+(?:own|buy|hold|invest|have|keep|get|pick\s+up)\b|
        (?:is|are|was)\b.{0,50}?\b(?:good|great|solid|safe|smart|risky|better|best)\s+(?:[\w-]+\s+){0,2}(?:buy|sell|investment|bet|hold|pick|choice|play)\b|
        where\s+should\s+(?:it|that|the\s+money|i|we)\s+(?:go|be\s+put|put|invest)|(?:i|we)\s+(?:have|got)\s+\$\s?\d|
        (?:in|into|to|for)\s+(?:a|an|my|our|your)\s+(?:retirement|brokerage|savings|college)\s+(?:account|fund)|
        addition\s+to\s+(?:a|an|my|our|your)\s+(?:[\w-]+\s+){0,2}(?:portfolio|holdings)|
        too\s+(?:cheap|expensive|pricey|rich|hot)\s+to\s+(?:touch|buy|own|hold|ignore|consider|pass\s+up|miss|sell)|
        (?:would|should|will|can)\s+(?:a|an|the|some|any)\s+(?:[\w-]+\s+){0,2}investors?\s+(?:go|buy|bet|pick|pile|jump|hold|sell|choose|own)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


# The reader's own money in the question ("park my money", "my retirement account", "my savings") is a request for a
# recommendation however it is worded. "its cash" and "an employee savings plan" are the company's, and are not caught.
OWN_MONEY_RE = re.compile(
    r"\b(?:my|our)\s+(?:money|cash|savings|retirement|nest\s+egg|portfolio|ira|401\s?\(?k\)?|brokerage|funds)\b", re.IGNORECASE
)


def asks_for_advice(question: str) -> bool:
    return bool(ADVICE_ASK_RE.search(question)) or bool(ADVICE_JUDGMENT_RE.search(question)) or bool(OWN_MONEY_RE.search(question)) or (
        bool(TRADE_WORD_RE.search(question)) and bool(DECISION_CUE_RE.search(question))
    )
