"""Season 0 rules. Every tunable number in the game lives here and nowhere else.

The balance pass is only allowed to change this file, so anything a bot's behaviour
depends on has to be reachable from a Rules instance rather than hard-coded in sim.py.
Rules is frozen and copied with `dataclasses.replace`, which lets a test build a variant
ruleset (pk forced to 1.0, say) without mutating anything global.
"""
from dataclasses import asdict, dataclass, replace

SEASON = 0


@dataclass(frozen=True)
class Rules:
    # --- world -------------------------------------------------------------
    asset_hp: int = 30
    asset_radius: float = 25.0
    max_ticks: int = 600
    spawn_radius: float = 490.0

    # --- attacker ----------------------------------------------------------
    attacker_budget: float = 60.0
    attacker_launches_per_tick: int = 4
    striker_cost: float = 2.0
    striker_speed: float = 4.0
    striker_damage: int = 10
    decoy_cost: float = 0.5
    decoy_speed: float = 4.0

    # --- defender sensing --------------------------------------------------
    radar_range: float = 450.0
    track_noise_sigma: float = 6.0
    id_range: float = 150.0

    # --- defender interceptors --------------------------------------------
    interceptor_stock: int = 20
    interceptor_cost: float = 4.0
    interceptor_speed: float = 12.0
    interceptor_lifetime: int = 90
    interceptor_launches_per_tick: int = 2
    blast_radius: float = 10.0
    interceptor_kill_prob: float = 0.85

    # --- defender gun ------------------------------------------------------
    gun_range: float = 100.0
    gun_ammo: int = 400
    gun_cost: float = 0.1
    gun_pk_scale: float = 0.40      # kill chance = scale * (1 - d/range) + floor
    gun_pk_floor: float = 0.05

    def cost_of(self, drone_type: str) -> float:
        return self.striker_cost if drone_type == "striker" else self.decoy_cost

    def speed_of(self, drone_type: str) -> float:
        return self.striker_speed if drone_type == "striker" else self.decoy_speed

    def cheapest_drone(self) -> float:
        return min(self.striker_cost, self.decoy_cost)

    def gun_kill_prob(self, distance: float) -> float:
        if distance > self.gun_range:
            return 0.0
        return self.gun_pk_scale * (1.0 - distance / self.gun_range) + self.gun_pk_floor

    def as_dict(self) -> dict:
        return asdict(self)

    def tuned(self, **kw) -> "Rules":
        return replace(self, **kw)


SEASON0 = Rules()
