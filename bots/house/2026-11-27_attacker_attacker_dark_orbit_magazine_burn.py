"""Idea: Hide every striker beyond radar range on a slow orbit while a decoy ring spends the defender's whole magazine, then release them only after the last interceptor has burned out.

Target: 2026-10-02_defender_loiter_then_collapse.

Weakness
--------
The defender treats the first inbound ring it sees as "the release". It
launches its whole magazine at once, parks the interceptors over the asset,
then commits them all together at W ~ 47. It never keeps any stock in reserve
and never checks what the ring is made of.

The pairing that shows this is
2026-10-23_attacker_bait_count_then_clear_sky_wave vs this defender, which has
a mean score_defender of 0.034. In seed 0, 20 interceptors were launched at a
16-decoy ring for a single decoy kill (stock_left 0). The strikers then came in
at tick 295 against a gun alone, and the gun fired only 20 shots and killed 2.

What this bot does differently
------------------------------
The bait attacker leaves its strikers visible inside radar range. This bot
never lets the defender see a striker before the magazine is gone. Radar
range is 450 and the spawn radius is 490, so each striker is steered onto a
slow orbit at radius 482. That is outside radar coverage, and every striker
keeps its own evenly spaced slot. Only the 16 decoys (cost 8) fly in, as an
evenly spaced shrinking ring. That is exactly the shape the defender's
collapse logic is built for.

Release rule: once interceptors have been seen and none have been airborne for
several ticks, or a hard deadline passes, all 26 strikers are released on the
same tick from 26 bearings. They converge together, so the gun has roughly 25
ticks of point-blank time to stop 26 strikers, and 3 hits breach the asset.
"""

import math

NAME = "attacker_dark_orbit_magazine_burn"
ROLE = "attacker"

HOLD_R = 482.0
ORBIT_STEP = 0.016          # radians of slot advance per tick
N_DECOYS = 16
EARLIEST_RELEASE = 125
QUIET_TICKS = 6
HARD_RELEASE = 440

_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "decoys_sent": 0,
        "strikers_sent": 0,
        "slots": {},          # drone id -> slot index
        "seen_icpt": 0,
        "quiet": 0,
        "released": False,
        "phase": 0.0,
    })


reset()


def _f(v, d=0.0):
    try:
        x = float(v)
        if x != x or x in (float("inf"), float("-inf")):
            return d
        return x
    except Exception:
        return d


def act(obs):
    out = {"launch": [], "steer": {}}
    try:
        if not _state:
            reset()
        tick = int(_f(obs.get("tick", 0)))
        budget = _f(obs.get("budget", 0.0))
        rules = obs.get("rules", {}) or {}
        cap = int(_f(rules.get("attacker_launches_per_tick", 4), 4))
        s_cost = _f(rules.get("striker_cost", 2.0), 2.0)
        d_cost = _f(rules.get("decoy_cost", 0.5), 0.5)
        radar = _f(rules.get("radar_range", 450.0), 450.0)
        spawn = _f(rules.get("spawn_radius", 490.0), 490.0)
        hold_r = min(HOLD_R, spawn - 4.0)
        if hold_r <= radar + 2.0:
            hold_r = max(radar + 2.0, (radar + spawn) / 2.0)

        asset = obs.get("asset", {}) or {}
        apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        ax, ay = _f(apos[0]), _f(apos[1])

        # Plan the striker count from the budget left after the decoy ring.
        total_budget = _f(rules.get("attacker_budget", 60.0), 60.0)
        n_strikers_plan = int(max(0.0, total_budget - N_DECOYS * d_cost) // s_cost)
        n_strikers_plan = max(1, n_strikers_plan)

        # ---- launches ----
        launches = []
        spent = 0.0
        while len(launches) < cap:
            if _state["decoys_sent"] < N_DECOYS:
                if budget - spent < d_cost:
                    break
                i = _state["decoys_sent"]
                launches.append({"type": "decoy",
                                 "bearing": (360.0 * i / N_DECOYS) % 360.0})
                _state["decoys_sent"] += 1
                spent += d_cost
            elif not _state["released"] and _state["strikers_sent"] < n_strikers_plan:
                if budget - spent < s_cost:
                    break
                j = _state["strikers_sent"]
                launches.append({"type": "striker",
                                 "bearing": (360.0 * j / n_strikers_plan + 7.0) % 360.0})
                _state["strikers_sent"] += 1
                spent += s_cost
            else:
                break
        out["launch"] = launches

        # ---- interceptor watch ----
        icpts = obs.get("interceptors", []) or []
        n_icpt = len(icpts)
        if n_icpt > 0:
            _state["seen_icpt"] = max(_state["seen_icpt"], n_icpt)
            _state["quiet"] = 0
        else:
            _state["quiet"] += 1

        launching_done = (_state["decoys_sent"] >= N_DECOYS and
                          (_state["strikers_sent"] >= n_strikers_plan or budget < s_cost))
        if not _state["released"] and launching_done:
            if tick >= HARD_RELEASE:
                _state["released"] = True
            elif (tick >= EARLIEST_RELEASE and _state["seen_icpt"] > 0
                  and _state["quiet"] >= QUIET_TICKS):
                _state["released"] = True

        # ---- steering ----
        drones = obs.get("drones", []) or []
        strikers = [d for d in drones if d.get("type") == "striker"]
        _state["phase"] += ORBIT_STEP
        phase = _state["phase"]

        if _state["released"]:
            for d in strikers:
                did = d.get("id")
                if did is not None and d.get("waypoint") is not None:
                    out["steer"][did] = None
        else:
            slots = _state["slots"]
            for d in strikers:
                did = d.get("id")
                if did is not None and did not in slots:
                    slots[did] = len(slots)
            n_slots = max(n_strikers_plan, len(slots), 1)
            for d in strikers:
                did = d.get("id")
                if did is None:
                    continue
                k = slots.get(did, 0)
                base = 2.0 * math.pi * k / n_slots
                pos = d.get("pos", [ax + hold_r, ay]) or [ax + hold_r, ay]
                px, py = _f(pos[0]) - ax, _f(pos[1]) - ay
                cur = math.atan2(py, px)
                target = base + phase
                # Rotate toward the slot, capped so the waypoint stays a few
                # units ahead and is never reached within a single tick.
                diff = (target - cur + math.pi) % (2.0 * math.pi) - math.pi
                step = max(-0.03, min(0.03, diff))
                if abs(step) < 0.012:
                    step = 0.012 if step >= 0 else -0.012
                ang = cur + step
                wx = ax + hold_r * math.cos(ang)
                wy = ay + hold_r * math.sin(ang)
                out["steer"][did] = [wx, wy]
    except Exception:
        return {"launch": [], "steer": {}}
    return out
