"""Look for safe rear angles and disengage until fully healed."""
import math
from collections import deque

import mechfight as mf
from navigation_bot import Bot as NavigationBot


class Bot(NavigationBot):
    name = "recovery-py"
    damage_window = 2.0
    cover_distances = (3, 5, 10)

    def __init__(self, hello):
        super().__init__(hello)
        self.recovering = False
        self.recent_threats = {}
        self.damage_samples = deque()
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

    def retreat_move(self, obs, base):
        me = obs["self"]
        x, y, z = me["pos"]
        height = me["stats"].get("height", 9)
        threats = {enemy["id"]: enemy for enemy in self.enemies}
        for enemy_id, (_, threat) in self.recent_threats.items():
            threats.setdefault(enemy_id, threat)
        exposed = [
            threat for threat in threats.values()
            if self.has_line(threat, (x, y, z + height / 2))
        ]
        if not exposed:
            return (0.0, 0.0)

        def score(point):
            px, py, ground = point
            body = (px, py, ground + height / 2)
            exposure = sum(self.has_line(threat, body) for threat in threats.values())
            separation = min(math.dist((px, py), threat["pos"][:2]) for threat in exposed)
            return exposure, -separation

        # Standing still is an explicit option. A route must reduce exposure
        # or increase separation at equal exposure to displace it.
        best = score(me["pos"])
        chosen = (0.0, 0.0)
        for reach in self.cover_distances:
            for heading, point in self.walk_options(obs, base, reach):
                candidate = score(point)
                if candidate < best:
                    chosen, best = heading, candidate
            if best[0] == 0:
                break
        return chosen

    def movement(self, obs, target):
        move = super().movement(obs, target)
        me = obs["self"]
        if self.zone_urgent(obs):
            return move
        if not me["grounded"]:
            if self.recovering:
                self.last_move = (0.0, 0.0)
                return self.last_move
            return move

        height = me["stats"].get("height", 9)
        if self.recovering:
            move = self.retreat_move(obs, move)
        elif self.clear_shot and target and len(self.exposed) == 1 and self.exposed[0]["id"] == target["id"]:
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

    def remember_threats(self, obs):
        now = obs["t"]
        self.recent_threats = {
            key: entry for key, entry in self.recent_threats.items() if entry[0] > now
        }
        actors = {actor["id"]: actor for actor in obs["mechs"]}
        for actor_id in self.recent_threats.keys() & actors.keys():
            expires, _ = self.recent_threats[actor_id]
            self.recent_threats[actor_id] = (expires, actors[actor_id])
        x, y, z = obs["self"]["pos"]
        for event in obs["events"]:
            if event["type"] != "damaged" or event.get("bearing") is None:
                continue
            actor_id = event.get("by")
            threat = actors.get(actor_id)
            if threat is None:
                bearing = event["bearing"]
                # Only the direction is known. Use a short-lived estimate.
                threat = {"pos": (x + 35 * math.cos(bearing), y + 35 * math.sin(bearing), z)}
                if actor_id in self.recent_threats:
                    threat = self.recent_threats[actor_id][1]
                self.recent_threats[actor_id] = (now + 3, threat)
            else:
                self.recent_threats[actor_id] = (now + 6, threat)

    def incoming_damage_rate(self, obs):
        now = obs["t"]
        while self.damage_samples and self.damage_samples[0][0] <= now - self.damage_window:
            self.damage_samples.popleft()
        damage = sum(
            event["amount"] for event in obs["events"]
            if event["type"] == "damaged" and event["weapon"] != "zone"
        )
        if damage > 0:
            self.damage_samples.append((now, damage))
        if not self.damage_samples or now - self.damage_samples[-1][0] > 0.75:
            return 0.0
        return sum(amount for _, amount in self.damage_samples) / self.damage_window

    def time_to_cover(self, obs):
        me = obs["self"]
        height = me["stats"].get("height", 9) / 2
        x, y, z = me["pos"]
        threats = {enemy["id"]: enemy for enemy in obs["mechs"] if enemy["kind"] == "mech"
                   and math.dist(me["pos"], enemy["pos"]) <= 300}
        for enemy_id, (_, threat) in self.recent_threats.items():
            threats.setdefault(enemy_id, threat)
        if not any(self.has_line(threat, (x, y, z + height)) for threat in threats.values()):
            return 0.0
        speed = me["stats"]["walk_speed"]
        if any(weapon and weapon.get("charge", 0) > 0 for weapon in me["weapons"]):
            speed *= 0.5
        for reach in self.cover_distances:
            for _, (px, py, ground) in self.walk_options(obs, self.last_move, reach):
                if not any(self.has_line(threat, (px, py, ground + height)) for threat in threats.values()):
                    return reach / max(1, speed) + 0.75
        # No nearby route blocks all firing lines. Use a conservative planning window.
        return 3.0

    def act(self, obs):
        me = obs["self"]
        self.remember_threats(obs)
        damage_rate = self.incoming_damage_rate(obs)
        if me["hp"] < 0.5 * me["max_hp"]:
            self.recovering = True
        elif me["hp"] >= me["max_hp"]:
            self.recovering = False
        elif not self.recovering and damage_rate > 0 and me["hp"] / damage_rate <= self.time_to_cover(obs):
            self.recovering = True
        if self.recovering and not self.zone_urgent(obs):
            self.climb = None
        action = super().act(obs)
        if self.recovering:
            action["fire"] = [False, False]
            if not any(action["move"]):
                action["jump"] = False
        return action


if __name__ == "__main__":
    mf.run(Bot)
