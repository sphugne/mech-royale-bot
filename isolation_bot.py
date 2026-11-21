"""Commit to finishable targets and break overlapping enemy firing lines."""
import math

import mechfight as mf
from combat_bot import direction
from evasion_bot import Bot as EvasionBot


class Bot(EvasionBot):
    name = "isolation-py"
    protect_zone_progress = True

    def __init__(self, hello):
        super().__init__(hello)
        self.target_id = None
        self.attackers = {}
        self.enemies = []
        self.exposed = []
        self.gun_range = 0
        self.now = 0

    def act(self, obs):
        me = obs["self"]
        self.now = obs["t"]
        self.gun_range = me["weapons"][0]["stats"]["range"]
        self.attackers = {
            attacker: expires for attacker, expires in self.attackers.items()
            if expires >= self.now
        }
        for event in obs["events"]:
            if event["type"] == "damaged" and event["by"] is not None:
                self.attackers[event["by"]] = self.now + 0.7

        position = me["pos"]
        self.enemies = [
            enemy for enemy in obs["mechs"]
            if enemy["kind"] == "mech" and math.dist(position, enemy["pos"]) <= 300
        ]
        body_height = me["stats"].get("height", 9) / 2
        body = (*position[:2], position[2] + body_height)
        self.exposed = [enemy for enemy in self.enemies if self.has_line(enemy, body)]
        return super().act(obs)

    def has_line(self, enemy, body):
        ex, ey, ez = enemy["pos"]
        muzzle = (ex, ey, ez + 7 * (1 + 0.05 * enemy.get("cubes", 0)))
        return not self.arena.blocked(muzzle, body)

    def dodge_allowed(self, obs, base, move, base_end, end):
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        center = zone["next_center"]
        if self.zone_urgent(obs) and math.dist(end, center) > max(
            0, zone["next_radius"] - 8, min(math.dist((x, y), center), math.dist(base_end, center))
        ) + 0.5:
            return False

        # Check both the immediate dodge and where its heading leads.
        height = me["stats"].get("height", 9) / 2
        def exposure(point):
            return sum(self.has_line(enemy, (*point, z + height)) for enemy in self.enemies)

        if exposure(end) > exposure(base_end):
            return False
        if len(self.exposed) >= 2:
            planned = (x + 9 * base[0], y + 9 * base[1])
            redirect = (x + 9 * move[0], y + 9 * move[1])
            return exposure(redirect) <= exposure(planned)
        return True

    def select_target(self, me, muzzle, enemies):
        # Within the same 5 m distance band, prefer the opponent with lower HP.
        ordered = sorted(enemies, key=lambda enemy: (
            int(math.dist(me["pos"], enemy["pos"]) / 5),
            enemy.get("hp", math.inf),
            math.dist(me["pos"], enemy["pos"]),
        ))
        available = {}
        for enemy in ordered:
            x, y, z = enemy["pos"]
            if (math.dist(me["pos"], enemy["pos"]) <= self.gun_range
                    and not self.arena.blocked(muzzle, (x, y, z + 4.5))):
                available[enemy["id"]] = enemy

        current = available.get(self.target_id)
        immediate = next((
            enemy for enemy in available.values()
            if enemy["id"] in self.attackers
            and (current is None or math.dist(me["pos"], enemy["pos"]) + 12
                 < math.dist(me["pos"], current["pos"]))
        ), None)
        target = immediate or current or next(iter(available.values()), None)
        self.clear_shot = target is not None
        self.target_id = target["id"] if target else None
        return target or (ordered[0] if ordered else None)

    def movement(self, obs, target):
        move = super().movement(obs, target)
        me, zone = obs["self"], obs["zone"]
        if not me["grounded"] or self.zone_urgent(obs):
            return move

        x, y, z = me["pos"]

        if len(self.exposed) >= 2:
            # Choose a nearby endpoint with fewer firing lines and a clear walking path.
            threats = self.exposed
            body_height = me["stats"].get("height", 9) / 2
            best = (len(threats), math.inf)
            for index in range(8):
                angle = index * math.tau / 8
                step = (math.cos(angle), math.sin(angle))
                px, py = x + 9 * step[0], y + 9 * step[1]
                if math.dist((px, py), zone["center"]) >= zone["radius"] - 2:
                    continue
                ground = self.arena.height(px, py)
                if abs(ground - z) > 1.2 or self.arena.blocked((x, y, z + 1), (px, py, ground + 1)):
                    continue
                body = (px, py, ground + body_height)
                exposure = sum(self.has_line(enemy, body) for enemy in self.enemies)
                if exposure >= len(threats):
                    continue
                score = (exposure, math.dist(step, move))
                if score < best:
                    move, best = step, score
        elif target and self.clear_shot:
            secondary = me["weapons"][1]
            if secondary and secondary["kind"] == "lightning" and me["hp"] > 0.45 * me["max_hp"]:
                stats = secondary["stats"]
                dx, dy = target["pos"][0] - x, target["pos"][1] - y
                if me["weapons"][0].get("reload", 0) > 0 and (
                    secondary["cooldown"] > 0 or math.dist(me["pos"], target["pos"]) > stats["range"]
                ):
                    return move
                if me["energy"] >= 5 * stats.get("energy", 3):
                    forward_x, forward_y = direction(dx, dy)
                    desired = 0.75 * stats["range"]
                    approach = max(-0.8, min(1.5, (math.hypot(dx, dy) - desired) / 15))
                    step = direction(approach * forward_x - 0.65 * self.side * forward_y,
                                     approach * forward_y + 0.65 * self.side * forward_x)
                    end = (x + 5 * step[0], y + 5 * step[1])
                    if (math.dist(end, zone["center"]) < zone["radius"] - 2
                            and not self.arena.blocked((x, y, z + 1), (*end, z + 1))):
                        move = step
        self.last_move = move
        return move


if __name__ == "__main__":
    mf.run(Bot)
