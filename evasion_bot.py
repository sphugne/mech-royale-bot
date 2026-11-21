"""Cover-aware combat with seeded strafes and short-horizon evasion."""
import math
import random

import mechfight as mf
from cover_bot import Bot as CoverBot


class Bot(CoverBot):
    name = "evasion-py"

    def __init__(self, hello):
        super().__init__(hello)
        self.rng = random.Random(hello["seed"])
        self.strafe_interval = self.rng.uniform(0.65, 1.65)
        self.weapons = hello["config"]["weapons"]

    def dodge_allowed(self, obs, base, move, base_end, end):
        return True

    def act(self, obs):
        previous_turn = self.last_turn
        action = super().act(obs)
        if self.last_turn != previous_turn:
            self.strafe_interval = self.rng.uniform(0.65, 1.65)

        me, zone = obs["self"], obs["zone"]
        if not me["grounded"] or not me["in_zone"]:
            return action
        x, y, z = me["pos"]
        projectiles = [
            shot for shot in obs["projectiles"]
            if math.dist(shot["pos"], me["pos"]) < (65 if shot["kind"] == "mortar" else 140)
        ][:24]
        lasers = [
            enemy for enemy in obs["mechs"]
            if enemy.get("charging") and math.dist(enemy["pos"], me["pos"]) < 280
        ]
        if not projectiles and not lasers:
            return action

        stats = me["stats"]
        size = 1 + 0.05 * me["cubes"]
        radius, height = stats.get("radius", 2.5 * size), stats.get("height", 9 * size)
        # A gun round travels about 2.5 m in 10 ms at default speed.
        times = tuple(step / 100 for step in range(1, 51))
        shots = []
        for shot in projectiles:
            px, py, pz = shot["pos"]
            vx, vy, vz = shot["vel"]
            mortar = shot["kind"] == "mortar"
            gravity = self.weapons["mortar"]["gravity"] if mortar else 0
            blast = self.weapons["mortar"]["splash_radius"] if mortar else 0
            for index, t in enumerate(times):
                point = (px + t * vx, py + t * vy, pz + t * vz - gravity * t * t / 2)
                if mortar and point[2] <= self.arena.height(*point[:2]):
                    shots.append((index, point, blast))
                    break
                shots.append((index, point, 0))

        beams = []
        for enemy in lasers:
            yaw, pitch = enemy["aim"]
            ex, ey, ez = enemy["pos"]
            muzzle = (ex, ey, ez + 7 * (1 + 0.05 * enemy.get("cubes", 0)))
            ray = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            if not self.arena.blocked(muzzle, (x, y, z + height / 2)):
                beams.append((muzzle, ray))

        base = tuple(action["move"])
        rushing = zone["shrink_end"] - obs["t"] < 6
        next_distance = math.dist((x, y), zone["next_center"])
        walk = stats["walk_speed"]
        boost = stats["boost_speed"]
        charging = any(weapon and weapon.get("charge", 0) > 0 for weapon in me["weapons"])
        factor = 0.5 if charging else 1
        acceleration = stats.get("ground_accel", 58.5)
        vx, vy = me["vel"][:2]

        def trajectory(move, speed):
            points = []
            px, py, ux, uy = x, y, vx, vy
            last_time = 0
            for time in times:
                dt = time - last_time
                dx, dy = move[0] * speed * factor - ux, move[1] * speed * factor - uy
                length = math.hypot(dx, dy)
                ratio = min(1, acceleration * dt / length) if length else 0
                px += dt * (ux + dx * ratio / 2)
                py += dt * (uy + dy * ratio / 2)
                ux, uy = ux + dx * ratio, uy + dy * ratio
                points.append((px, py))
                last_time = time
            return points

        def risk(points):
            cost = 0.0
            for index, (px, py, pz), blast in shots:
                bx, by = points[index]
                horizontal = math.hypot(px - bx, py - by)
                if blast:
                    if abs(pz - z) <= blast:
                        cost += max(0, 1 - horizontal / (radius + blast)) * 4
                elif z - 0.5 <= pz <= z + height + 0.5:
                    cost += max(0, 1 - horizontal / (radius + 1)) * 2
            for muzzle, ray in beams:
                for index, weight in ((14, 0.7), (24, 0.6), (39, 0.4)):
                    bx, by = points[index]
                    offset = (bx - muzzle[0], by - muzzle[1], z + height / 2 - muzzle[2])
                    along = sum(a * b for a, b in zip(offset, ray))
                    if 0 <= along <= 280:
                        miss = math.dist(offset, tuple(along * component for component in ray))
                        cost += weight * max(0, 1 - miss / max(radius + 2, height / 2))
            return cost

        base_points = trajectory(base, walk)
        best_risk = risk(base_points)
        if best_risk == 0:
            return action
        chosen, use_boost = base, False
        for index in range(8):
            angle = index * math.tau / 8
            move = (math.cos(angle), math.sin(angle))
            for speed, boosted in ((walk, False), (boost, True)):
                if boosted and me["energy"] < 20:
                    continue
                points = trajectory(move, speed)
                end = points[-1]
                if math.dist(end, zone["center"]) > zone["radius"]:
                    continue
                if rushing and next_distance > zone["next_radius"] and math.dist(end, zone["next_center"]) > next_distance:
                    continue
                cost = risk(points) + 0.12 * math.dist(move, base) + 0.12 * boosted
                if (cost < best_risk
                        and not self.arena.blocked((x, y, z + 1), (*end, z + 1))
                        and self.dodge_allowed(obs, base, move, base_points[-1], end)):
                    chosen, use_boost, best_risk = move, boosted, cost

        action["move"] = chosen
        action["boost"] = use_boost
        self.last_move = chosen
        return action


if __name__ == "__main__":
    mf.run(Bot)
