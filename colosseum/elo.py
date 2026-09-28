"""Two Elo ladders, one per role.

Attackers and defenders never play their own kind, so a single pool would be meaningless:
a rating only says "how this bot does against the other side". Ratings are still updated
against each other across the two pools, which is standard for asymmetric games.

The continuous match score is used as the Elo result rather than win/loss, so a defender
that holds the asset at 29 HP is rewarded over one that survives at 1 HP.
"""
K = 24.0
START = 1000.0


def expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update(rating_a: float, rating_b: float, score_a: float, k: float = K):
    """Returns the pair of new ratings. score_a is in [0, 1]; score_b is 1 - score_a."""
    exp_a = expected(rating_a, rating_b)
    delta = k * (score_a - exp_a)
    return rating_a + delta, rating_b - delta


class Ladders:
    def __init__(self, attackers, defenders, k: float = K):
        self.k = k
        self.attackers = {name: START for name in attackers}
        self.defenders = {name: START for name in defenders}

    def record(self, attacker: str, defender: str, score_attacker: float):
        ra, rd = self.attackers[attacker], self.defenders[defender]
        new_a, new_d = update(ra, rd, score_attacker, self.k)
        self.attackers[attacker] = new_a
        self.defenders[defender] = new_d
