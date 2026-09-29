# Season one

Swarm Colosseum, run by Pelennor.

| | |
|---|---|
| first night | **2026-09-28** (`staggered_screen_trickle` and `discriminating_ledger` written) |
| last night | **2026-10-25** |
| ends | **2026-10-26**, four weeks after the first real night |
| weekly meta reports | after real nights 7, 14, 21 and 28 |

`rules.py` is frozen until the season ends. In code this season is `SEASON = 0` and every
replay says `season: 0`; the counter started at zero before the season had a name, and
renaming it would change every replay's bytes. "Season one" and "season 0" are the same
season.

Season-two rule candidates are tested on the `season2-candidates` branches and are never
merged during season one. See `SEASON2_CANDIDATES.md` on that branch.

## Approved for season two

| | branch | merge on |
|---|---|---|
| candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) | `s2-a-imperfect-id`, kept rebased on master | **2026-10-26**, not before |

Decided 2026-09-29. The S0-2 economy fix is deferred until the seven-night watch on
`synchronized_ring` ends (nights 2026-09-30 to 2026-10-06, `out/WATCH.md`).
