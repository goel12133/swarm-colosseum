# Engine scoping: more texture for the game (backlog 3.12)

Written 2026-10-03. Two pages. It scopes four engine features that would give strategy more
texture. **This is game design.** Every unit is made up (`u`, `ticks`, `credits`, `bands`).
Nothing here describes or stands for a real system. The arena makes no claim that a result
in it predicts anything outside it, and this document doesn't add one. Nothing is built yet.
`rules.py` is frozen until the boundary (2026-10-26), and season two is already set
(candidate A). Whatever we pick from here goes to a branch for a later season.

## Where the game is thin today

- **Sensing is one number.** Every drone inside 450 u is seen every tick, with the same
  Gaussian noise (σ = 6 u) at every range. No track ever drops and no track is ever false.
- **Classification is a cliff.** At 150 u a track goes from `unknown` to its true type, and
  it is never wrong. A decoy only works by being unidentified, never by being mistaken.
- **The world is flat and turns are free.** Drones and interceptors change heading
  instantly. A bad lead costs nothing, so geometry barely matters. That is why `flanker`
  wins 0% (ROADMAP, open questions).

The library shows the cost: 9 families, but season one has been decided by timing and
budgeting (synchronised arrival, blast packing). Space and uncertainty matter very little.

## Four features, each a handful of Rules fields

Each field's default reproduces today's engine exactly. See "Determinism" below.

**1. Noisy sensors with dropouts and false tracks.**
Fields: `track_noise_growth` (extra σ per 100 u of range, default 0),
`track_dropout_prob` (chance a real track is missing from a tick's report, default 0),
`false_track_rate` (expected phantom tracks per tick, default 0), `false_track_life`
(ticks a phantom persists, default 0).
Texture: defenders have to keep track memory and confirm before committing stock.
Attackers gain from approaching where noise is high. Phantoms give the interceptor
retarget order a real job.
Observation: no new keys. A phantom is a track with an id that never impacts. Firing at
one is legal and simply wasted.
Size: ~60 engine lines, ~10 tests. Low risk.

**2. Classification confusion instead of a cliff.**
Fields: `id_confusion_far` (chance of a wrong label at the edge of sensor range),
`id_confusion_near` (at `id_range`), both default 0. In between, interpolate linearly. Add
`cls_conf` (0–1) to each track.
Texture: decoys can be *mislabelled*, not just hidden. Identify-first defenders now have
to trade waiting against certainty, which is the trade-off the gun-ammo cut was meant to
create. It's also a direct test of whether decoys are priced right at 0.5 credits (an open
ROADMAP question).
Observation: one new key, `cls_conf`. Old bots ignore it.
Size: ~30 lines, ~8 tests. Low risk. **Recommended first.**

**3. Turn rates.**
Fields: `drone_turn_deg` and `interceptor_turn_deg` (max heading change per tick, default
180, which is the same as unlimited).
Texture: leading a target becomes a skill, and crossing approaches cost the defender
interceptors that miss. Spread geometry (`flanker`) becomes a real idea. Attackers who
steer late pay for it with a wide arc.
Observation: none new. Heading is already implied by `vel`.
Size: ~25 lines plus a clamp helper, ~8 tests (including "at 180 the replay is
byte-identical"). Medium risk: it changes how interceptor guidance feels, so baselines may
need retuning. **Recommended second.**

**4. Altitude bands.**
Fields: `bands` (default 1), and per band: a sensor-range multiplier, a gun reach flag, a
speed multiplier, and `band_change_ticks` (ticks spent moving between bands).
Texture: a third axis to trade off. A high band is fast and seen early. A low band is
seen late but in gun reach. Attackers can split a wave across bands. Defenders have to
choose which band they spend stock on.
Observation: `band` on each drone and track, `band` on launch and steer orders. The
action schema changes, so the validator (`policy.py`, `submit.check_source`), the viewer
and the workshop kit all change too.
Size: ~120 engine lines, viewer work, ~20 tests. Highest risk and the biggest bot-API
change. **Last, and only if 1–3 aren't enough.**

## Constraints any build must keep

- **Determinism.** New random draws happen only when a feature's probability is non-zero.
  They are drawn in sorted-id order from the match's single RNG, with `normalvariate`, never
  `gauss`. With every field at its default, a test checks that all seeds of a fixed
  attacker × defender set give byte-identical replays against today's engine. The engine
  version changes anyway, so the cache goes cold for one night. That is expected.
- **Bot compatibility.** Existing observation keys keep their meaning and only additions
  are allowed. Every live bot must still run without errors under default Rules (the
  invariant 3.9 already checks for policy errors).
- **Fuzzer.** `colosseum.fuzz` grows to cover the new fields: phantom ids in actions,
  turn clamps never exceeded, bands always in range.
- **Abstract only.** Field names describe game mechanics, not equipment. No default is
  chosen to match anything real. Defaults are tuned against the ladder like every
  balance change, and logged in `BALANCE.md`.

## How we would know it worked

Measured in the game, on a candidate branch, over seven nights, like S0-2: more occupied
tactic families in the library, more bots with unique coverage, no bot above 90%, and both
roles inside 40–60%. If a feature adds rules without adding families, we drop it.

## Proposed order

2 (confusion) → 3 (turn rates) → 1 (sensors) on `season3-candidates` after the season-two boundary work, one feature per
branch, each behind neutral defaults. Altitude bands only after a founder decision. Effort
for 1–3: about three build sessions.

## Out of scope, and one question for the founder

Out of scope: matching any real sensor or platform, real-world transfer experiments, and
any claim that tactics carry over. `ROADMAP.md` (Stage 3) still lists "a paid API for a
company to test its own defence logic against the accumulated attack library". That
conflicts with the scope decision of 2026-10-03, and this document does not plan for it.
**Founder: remove or rewrite that ROADMAP line? (yes/no)**
