"""Rejoin useful routes when shots are blocked, with bounded jump-and-jet recovery."""
import math
from dataclasses import dataclass

import mechfight as mf
from isolation_bot import Bot as IsolationBot


@dataclass
class Climb:
    heading: tuple[float, float]
    clearance: float
    expires: float
    crossing: bool = False


class Bot(IsolationBot):
    name = "navigation-py"

    def __init__(self, hello):
        super().__init__(hello)
        self.climb = None
        self.retry_at = 0.0

    def pursuit_target(self, target):
        # Reload cover still receives the original target as a threat.
        return target if self.clear_shot else None

    def climb_heading_safe(self, obs, heading):
        me, zone = obs["self"], obs["zone"]
        x, y = me["pos"][:2]
        end = (x + 8 * heading[0], y + 8 * heading[1])
        current_distance = math.dist((x, y), zone["center"])
        if math.dist(end, zone["center"]) > max(zone["radius"], current_distance):
            return False
        if self.zone_urgent(obs):
            center = zone["next_center"]
            return math.dist(end, center) <= max(
                zone["next_radius"], math.dist((x, y), center)
            )
        return True

    def clearance_height(self, me, heading):
        x, y, z = me["pos"]
        dx, dy = heading
        reach = 8.0
        body_height = me["stats"].get("height", 9)
        dest = (x + reach * dx, y + reach * dy)

        def clear_at(feet):
            return all(
                not self.arena.blocked((x, y, feet + offset), (*dest, feet + offset))
                for offset in (0.3, body_height - 0.3)
            )

        if clear_at(z + 1.2):
            return None
        for rise in (2, 3.5, 5, 6.5, 8):
            feet = z + rise
            if self.arena.blocked((x, y, z + body_height - 0.3), (x, y, feet + body_height)):
                return None
            if clear_at(feet):
                return feet
        return None

    def act(self, obs):
        stalled_heading = self.last_move
        action = super().act(obs)
        me = obs["self"]
        now = obs["t"]
        z = me["pos"][2]

        if self.climb is None:
            # The stall was measured on the previous command. A new dodge or
            # detour takes precedence if it points in a different direction.
            same_route = sum(a * b for a, b in zip(stalled_heading, action["move"])) >= 0.7
            if (now < self.retry_at or not action["jump"] or not same_route
                    or me["energy"] < 25 or (len(self.exposed) >= 2 and not self.zone_urgent(obs))
                    or not self.climb_heading_safe(obs, stalled_heading)):
                return action
            clearance = self.clearance_height(me, stalled_heading)
            if clearance is None:
                return action
            self.climb = Climb(stalled_heading, clearance, now + 2.0)
            self.retry_at = now + 5.0
            action["move"] = stalled_heading
            self.last_move = stalled_heading
            return action

        climb = self.climb
        if (now >= climb.expires or me["energy"] < 12 or me["grounded"]
                or (len(self.exposed) >= 2 and not self.zone_urgent(obs))
                or not self.climb_heading_safe(obs, climb.heading)):
            self.climb = None
            return action

        if not climb.crossing and z >= climb.clearance:
            climb.crossing = True
            climb.expires = min(climb.expires, now + 0.75)

        action["move"] = climb.heading
        action["boost"] = not climb.crossing
        action["jump"] = False
        self.last_move = climb.heading
        return action


if __name__ == "__main__":
    mf.run(Bot)
