"""Use nearby corners to shoot one opponent and reload behind cover."""
import math

import mechfight as mf
from duel_bot import Bot as DuelBot


class Bot(DuelBot):
    name = "choke-py"

    def dodge_allowed(self, obs, base, move, base_end, end):
        if not super().dodge_allowed(obs, base, move, base_end, end):
            return False
        if self.corner_target is None:
            return True
        z = obs["self"]["pos"][2]
        height = obs["self"]["stats"].get("height", 9) / 2
        return not any(
            enemy["id"] != self.corner_target and self.has_line(enemy, (*end, z + height))
            for enemy in self.enemies
        )

    def movement(self, obs, target):
        self.corner_target = None
        base = super().movement(obs, target)
        me = obs["self"]
        if (not target or not me["grounded"] or self.zone_urgent(obs)
                or len(self.exposed) > 1 or math.dist(me["pos"], target["pos"]) > 85):
            return base

        position = me["pos"]
        height = me["stats"].get("height", 9) / 2
        muzzle_height = me["stats"].get("muzzle_height", 7)
        target_id = target["id"]
        if self.exposed and self.exposed[0]["id"] != target_id:
            return base

        def opponents_with_line(point):
            body = (*point[:2], point[2] + height)
            return {enemy["id"] for enemy in self.enemies if self.has_line(enemy, body)}

        def isolated_path(point):
            midpoint = tuple((start + end) / 2 for start, end in zip(position, point))
            return opponents_with_line(midpoint) <= {target_id}

        def can_shoot(point):
            muzzle = (*point[:2], point[2] + muzzle_height)
            body = (*target["pos"][:2], target["pos"][2] + 4.5)
            return not self.arena.blocked(muzzle, body)

        gun = me["weapons"][0]
        reloading = gun.get("reload", 0) > 0 or gun.get("ammo", 0) == 0
        sheltered = not self.exposed

        # The current location supplies one end of the corner. Search for a
        # walkable counterpart on the other side of the firing line.
        if sheltered and reloading:
            if not self.clear_shot:
                return self.set_move((0.0, 0.0), target_id)
            return base
        if sheltered and self.clear_shot:
            return self.set_move((0.0, 0.0), target_id)
        if not sheltered and not self.clear_shot and not reloading:
            return base

        for reach in (3, 7):
            for heading, point in self.walk_options(obs, base, reach):
                exposure = opponents_with_line(point)
                if sheltered:
                    counterpart = exposure <= {target_id} and can_shoot(point)
                else:
                    counterpart = not exposure
                if not counterpart or not isolated_path(point):
                    continue
                if sheltered or reloading:
                    return self.set_move(heading, target_id)
                # While shooting, keep the reload shelter within one move.
                return self.set_move((0.0, 0.0), target_id)
        return base

    def set_move(self, move, target_id):
        self.last_move = move
        self.corner_target = target_id
        return move


if __name__ == "__main__":
    mf.run(Bot)
