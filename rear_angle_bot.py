"""Test rear-angle positioning with the navigation bot's normal combat."""
import math

import mechfight as mf
from navigation_bot import Bot as NavigationBot


class Bot(NavigationBot):
    name = "rear-angle-py"

    def __init__(self, hello):
        super().__init__(hello)
        front_arc = hello["config"]["mech"].get("front_arc_deg", 180)
        self.front_edge = math.radians(front_arc / 2)

    def rear_angle(self, target, point):
        x, y, _ = target["pos"]
        bearing = math.atan2(point[1] - y, point[0] - x)
        return abs(math.remainder(bearing - target["aim"][0], math.tau))

    def walk_options(self, obs, base, reach):
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        height = me["stats"].get("height", 9)
        headings = [base] if any(base) else []
        headings.extend(
            (math.cos(index * math.tau / 8), math.sin(index * math.tau / 8))
            for index in range(8)
        )
        for heading in headings:
            px, py = x + reach * heading[0], y + reach * heading[1]
            if math.dist((px, py), zone["center"]) > zone["radius"] - 2:
                continue
            ground = self.arena.height(px, py)
            if abs(ground - z) > 1.2 or any(
                self.arena.blocked((x, y, z + offset), (px, py, ground + offset))
                for offset in (1, height - 0.3)
            ):
                continue
            yield heading, (px, py, ground)

    def movement(self, obs, target):
        move = super().movement(obs, target)
        me = obs["self"]
        if self.zone_urgent(obs) or not me["grounded"]:
            return move

        height = me["stats"].get("height", 9)
        if self.clear_shot and target and len(self.exposed) == 1 and self.exposed[0]["id"] == target["id"]:
            distance = math.dist(me["pos"], target["pos"])
            if distance <= 85 and me["weapons"][0].get("reload", 0) <= 0:
                best_angle = self.rear_angle(target, me["pos"])
                muzzle_height = me["stats"].get("muzzle_height", 7)
                target_body = (*target["pos"][:2], target["pos"][2] + 4.5)
                for heading, point in self.walk_options(obs, move, 8):
                    angle = self.rear_angle(target, point)
                    if angle < self.front_edge or angle < best_angle + math.radians(3):
                        continue
                    if math.dist(point, target["pos"]) > distance + 3:
                        continue
                    body = (*point[:2], point[2] + height / 2)
                    if any(enemy["id"] != target["id"] and self.has_line(enemy, body) for enemy in self.enemies):
                        continue
                    muzzle = (*point[:2], point[2] + muzzle_height)
                    if not self.arena.blocked(muzzle, target_body):
                        move, best_angle = heading, angle
        self.last_move = move
        return move


if __name__ == "__main__":
    mf.run(Bot)
