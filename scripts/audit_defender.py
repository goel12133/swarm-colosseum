"""Characterise a defender's results: per attacker, and whether the launch cap ever bound.

    python3 scripts/audit_defender.py bots/house/2026-09-28_defender_discriminating_ledger.py

The engine runs on the host; both bots run in the sandbox, so this is safe for house bots.
Per tick, after the defender's orders are applied, it records:

  launched      interceptors launched this tick (the cap is interceptor_launches_per_tick)
  at_cap        launched == cap
  binding       at_cap AND an identified striker was still left with no interceptor on it,
                i.e. the defender had a use for another launch and the cap stopped it
  waiting       identified strikers inside id range with no interceptor, after the orders

Prints JSON: per-attacker score/CER/outcomes, cap use, stock/ammo left, striker fates, and
the weakest matches (lowest score_defender) for replay review. Writes nothing.
"""
import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colosseum.rules import SEASON0                            # noqa: E402
from colosseum.sandbox import SandboxedPolicy, SandboxLimits   # noqa: E402
from colosseum.sim import Match                                # noqa: E402
from colosseum.tournament import _role_of, discover            # noqa: E402


class AuditMatch(Match):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ticks = []

    def _apply_defender(self, action):
        before = self.interceptors_launched
        super()._apply_defender(action)
        r = self.rules
        launched = self.interceptors_launched - before
        chased = {i.target for i in self._alive_interceptors()}
        waiting = sum(1 for d in self._alive_drones()
                      if d.type == "striker" and (d.x * d.x + d.y * d.y) ** 0.5 <= r.id_range
                      and d.id not in chased)
        at_cap = launched >= r.interceptor_launches_per_tick
        self.ticks.append(dict(t=self.tick, launched=launched, at_cap=at_cap,
                               binding=at_cap and waiting > 0 and self.stock > 0,
                               waiting=waiting, stock=self.stock))


def audit_one(job):
    attacker, defender, seed = job
    lim = SandboxLimits()
    a = SandboxedPolicy(attacker, "attacker", lim)
    try:
        d = SandboxedPolicy(defender, "defender", lim)
    except Exception:
        a.close()
        raise
    try:
        m = AuditMatch(a, d, seed, rules=SEASON0, record=True)
        res = m.run()
    finally:
        a.close()
        d.close()
    meta = res["meta"]
    kills = defaultdict(int)
    for e in res["events"]:
        if e["kind"] == "kill":
            kills[f"{e['dtype']}_by_{e['by']}"] += 1
    return dict(
        attacker=Path(attacker).stem, seed=seed,
        score_defender=meta["score_defender"], cer=meta["cost_exchange_ratio"],
        outcome=meta["outcome"], asset_hp=meta["asset_hp"], ticks=meta["ticks"],
        strikers_launched=meta["drones_launched"]["striker"],
        decoys_launched=meta["drones_launched"]["decoy"],
        strikers_impacted=meta["drones_impacted"]["striker"],
        decoys_killed=meta["drones_killed"]["decoy"],
        kills=dict(kills),
        interceptors_launched=meta["interceptors_launched"], stock_left=meta["stock_left"],
        shots_fired=meta["shots_fired"], ammo_left=meta["ammo_left"],
        ticks_at_cap=sum(t["at_cap"] for t in m.ticks),
        ticks_binding=sum(t["binding"] for t in m.ticks),
        max_waiting=max((t["waiting"] for t in m.ticks), default=0),
        min_stock=min((t["stock"] for t in m.ticks), default=SEASON0.interceptor_stock),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("defender")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    attackers = discover(ROOT / "bots" / "attackers") + [
        p for p in discover(ROOT / "bots" / "house") if _role_of(p) == "attacker"]
    jobs = [(str(a), args.defender, s) for a in sorted(attackers) for s in range(args.seeds)]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(audit_one, jobs))

    per = {}
    for name in sorted({r["attacker"] for r in rows}):
        rs = [r for r in rows if r["attacker"] == name]
        n = len(rs)
        per[name] = dict(
            matches=n,
            mean_score_defender=round(sum(r["score_defender"] for r in rs) / n, 3),
            mean_cer=round(sum(r["cer"] for r in rs) / n, 3),
            defended=sum(r["outcome"] == "defended" for r in rs),
            mean_hp_left=round(sum(r["asset_hp"] for r in rs) / n, 1),
            strikers_launched=round(sum(r["strikers_launched"] for r in rs) / n, 1),
            strikers_impacted=round(sum(r["strikers_impacted"] for r in rs) / n, 2),
            decoys_killed=sum(r["decoys_killed"] for r in rs),
            interceptors_used=round(sum(r["interceptors_launched"] for r in rs) / n, 1),
            min_stock_seen=min(r["min_stock"] for r in rs),
            matches_stock_exhausted=sum(r["stock_left"] == 0 for r in rs),
            mean_shots=round(sum(r["shots_fired"] for r in rs) / n, 1),
            ticks_at_cap=sum(r["ticks_at_cap"] for r in rs),
            ticks_binding=sum(r["ticks_binding"] for r in rs),
            max_waiting=max(r["max_waiting"] for r in rs),
        )
    weakest = sorted(rows, key=lambda r: r["score_defender"])[:4]
    print(json.dumps(dict(defender=Path(args.defender).stem, per_attacker=per,
                          weakest=weakest), indent=2))


if __name__ == "__main__":
    main()
