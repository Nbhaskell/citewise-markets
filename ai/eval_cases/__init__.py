"""The evaluation cases for `ai.eval_market`, in groups, and the lists the runner uses: `CASES`, `HELD_OUT`, `SEALED`.

The order of `CASES` is the order the cases run and print in, so a new group goes where it was written, not at random.
"""
from .common import Case
from .sealed import (
    SEALED_ROUND_FIVE,
    SEALED_ROUND_FOUR,
    SEALED_ROUND_ONE,
    SEALED_ROUND_THREE,
    SEALED_ROUND_TWO,
)
from .tuning_early import (
    ROUND_EIGHT,
    ROUND_ELEVEN,
    ROUND_FIVE,
    ROUND_FOUR,
    ROUND_NINE,
    ROUND_ONE,
    ROUND_SEVEN,
    ROUND_SIX,
    ROUND_TEN,
    ROUND_THIRTEEN,
    ROUND_THREE,
    ROUND_TWELVE,
    ROUND_TWO,
)
from .tuning_late import (
    ROUND_AW,
    ROUND_EIGHTEEN,
    ROUND_FIFTEEN,
    ROUND_FM,
    ROUND_FP,
    ROUND_FR,
    ROUND_FU,
    ROUND_LATELY,
    ROUND_NINETEEN,
    ROUND_RM,
    ROUND_SEVENTEEN,
    ROUND_SIXTEEN,
    ROUND_SL,
    ROUND_TWENTY,
    ROUND_TWENTYONE,
)

# Everything below that has been run and looked at is tuning material. ROUND_FM and SEALED_ROUND_ONE are both tuning
# material now (docs/DECISIONS.md, "Model-based routing experiment"): the 39 `fm` cases were the router's development
# set; the 38 `sb` cases were run once as the sealed test (keywords 78 of 114, router 90 of 114 on the final code, 93 on
# the first version) and then looked at, because they exposed a false decline. Write a new sealed set before the next
# fair comparison.
# SEALED_ROUND_TWO was partly spoiled (the "lately" rule), so it is tuning material from here on.
# SEALED_ROUND_THREE and SEALED_ROUND_FOUR were RUN once (2026-10-18 and 2026-10-19; DECISIONS: "Third sealed round",
# "Fourth sealed round") and every answer was read, so both are SPENT: they join `CASES`.
CASES: tuple[Case, ...] = (
    ROUND_ONE
    + ROUND_TWO
    + ROUND_THREE
    + ROUND_FOUR
    + ROUND_FIVE
    + ROUND_SIX
    + ROUND_SEVEN
    + ROUND_EIGHT
    + ROUND_NINE
    + ROUND_TEN
    + ROUND_ELEVEN
    + ROUND_TWELVE
    + ROUND_THIRTEEN
    + ROUND_FIFTEEN
    + ROUND_SIXTEEN
    + ROUND_SEVENTEEN
    + ROUND_EIGHTEEN
    + ROUND_NINETEEN
    + ROUND_TWENTY
    + ROUND_TWENTYONE
    + ROUND_FM
    + SEALED_ROUND_ONE
    + ROUND_SL
    + ROUND_LATELY
    + ROUND_FU
    + ROUND_FP
    + SEALED_ROUND_TWO
    + ROUND_AW
    + ROUND_RM
    + ROUND_FR
    + SEALED_ROUND_THREE
    + SEALED_ROUND_FOUR
)

# Fresh cases only (none have been run). Write new ones before claiming a fair score.
HELD_OUT: tuple[Case, ...] = ()

# The sealed test set: run only with `--sealed`, once, at the end of an experiment, and never tuned on.
# SEALED_ROUND_FIVE was RUN once on 2026-10-19 (46 cases: keywords only 30, router on 36; DECISIONS: "Fifth sealed round"),
# every answer was read, and it is SPENT; it stays here (out of `CASES`, out of the router shadow run) until a
# SEALED_ROUND_SIX replaces it, if there is one.
SEALED: tuple[Case, ...] = SEALED_ROUND_FIVE
