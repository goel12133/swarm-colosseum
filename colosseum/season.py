"""Season dates. SEASON.md is the human-readable copy; a test keeps the two in step.

Season one is `SEASON = 0` in rules.py and `season: 0` in every replay: the code counted from
zero before the season had a name, and renaming it would change every replay's bytes.
"""
from datetime import date, timedelta

NAME = "Season one"
NUMBER = 1                               # reports/SEASON_<NUMBER>.md, seasons/S<NUMBER>/
FIRST_NIGHT = date(2026, 9, 28)          # the night staggered_screen_trickle and
                                         # discriminating_ledger were written
LENGTH_NIGHTS = 28                       # four weeks
LAST_NIGHT = FIRST_NIGHT + timedelta(days=LENGTH_NIGHTS - 1)     # 2026-10-25
ENDS = FIRST_NIGHT + timedelta(days=LENGTH_NIGHTS)               # 2026-10-26
