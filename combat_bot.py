"""Fight while moving, with weapon-specific aim and zone-aware positioning."""
import math

import mechfight as mf


def direction(dx, dy):
    distance = math.hypot(dx, dy)
    return (dx / distance, dy / distance) if distance else (0.0, 0.0)


def gun_aim(origin, target, speed):
    # Iterate on flight time to lead a target moving at its observed velocity.
    tx, ty, tz = target["pos"]
    vx, vy, vz = target["vel"]
    offset = (tx - origin[0], ty - origin[1], tz + 4.5 - origin[2])
    flight = 0.0
    for _ in range(3):
        dx, dy, dz = (value + velocity * flight for value, velocity in zip(offset, (vx, vy, vz)))
        flight = max(0.0, math.sqrt(dx * dx + dy * dy + dz * dz) - 3.0) / speed
    return math.atan2(dy, dx), math.atan2(dz, math.hypot(dx, dy))


class Bot:
    name = "combat-py"
    strafe_interval = 1.25

    def __init__(self, hello):
        self.pickup_radius = hello["config"]["loot"]["pickup_radius"]
        self.side = 1 if hello["slot"] % 2 else -1
        self.last_turn = -10.0
        self.last_move = (0.0, 0.0)
        self.last_position = None
        self.last_time = None
        self.stalled_for = 0.0
        self.detour_until = 0.0
        self.detour = (0.0, 0.0)

    @staticmethod
    def zone_urgent(obs):
        me, zone = obs["self"], obs["zone"]
        remaining = math.dist(me["pos"][:2], zone["next_center"]) - max(0, zone["next_radius"] - 8)
        travel = 1.5 * remaining / max(1, me["stats"]["walk_speed"]) + 5
        return not me["in_zone"] or (remaining > 0 and obs["t"] + travel >= zone["shrink_end"])

    def movement(self, obs, target):
        me = obs["self"]
        zone = obs["zone"]
        x, y = me["pos"][:2]
        now = obs["t"]
        zone_dx, zone_dy = zone["next_center"][0] - x, zone["next_center"][1] - y
        if self.zone_urgent(obs):
            move = direction(zone_dx, zone_dy)
        elif target:
            dx, dy = target["pos"][0] - x, target["pos"][1] - y
            distance = math.hypot(dx, dy)
            forward_x, forward_y = direction(dx, dy)
            if now - self.last_turn > self.strafe_interval:
                self.side *= -1
                self.last_turn = now
            desired_range = 65 if me["hp"] > 0.45 * me["max_hp"] else 95
            approach = max(-0.85, min(0.65, (distance - desired_range) / 35))
            move = direction(approach * forward_x - self.side * forward_y,
                             approach * forward_y + self.side * forward_x)
        else:
            loot = min(
                (cube for cube in obs["cubes"] if abs(cube["pos"][2] - me["pos"][2]) <= 4),
                key=lambda cube: math.dist((x, y), cube["pos"][:2]),
                default=None,
            )
            if loot and math.dist((x, y), loot["pos"][:2]) <= 30:
                move = direction(loot["pos"][0] - x, loot["pos"][1] - y)
            else:
                move = direction(zone_dx, zone_dy) if math.hypot(zone_dx, zone_dy) > 4 else (0.0, 0.0)

        if self.last_position and any(self.last_move) and me["grounded"]:
            elapsed = now - self.last_time
            dx, dy = x - self.last_position[0], y - self.last_position[1]
            progress = dx * self.last_move[0] + dy * self.last_move[1]
            self.stalled_for = self.stalled_for + elapsed if 0 < elapsed <= 0.25 and progress < elapsed else 0.0
            if self.stalled_for >= 0.5 and now >= self.detour_until:
                self.detour = (-self.last_move[1] * self.side, self.last_move[0] * self.side)
                self.detour_until = now + 1.0
                self.stalled_for = 0.0
                self.side *= -1
        else:
            self.stalled_for = 0.0
        if now < self.detour_until and any(move):
            move = self.detour

        # Keep combat strafes and loot pursuit from drifting across the current edge.
        cx, cy = zone["center"]
        if me["in_zone"] and math.hypot(x + 5 * move[0] - cx, y + 5 * move[1] - cy) > zone["radius"]:
            move = direction(cx - x, cy - y)
        self.last_position = (x, y)
        self.last_time = now
        self.last_move = move
        return move

    def select_target(self, me, muzzle, enemies):
        return min(enemies, key=lambda enemy: math.dist(me["pos"], enemy["pos"]), default=None)

    def act(self, obs):
        me = obs["self"]
        x, y, z = me["pos"]
        gun, secondary = me["weapons"]
        muzzle = (x, y, z + me["stats"].get("muzzle_height", 7))
        enemies = [enemy for enemy in obs["mechs"] if enemy["kind"] == "mech"]
        target = self.select_target(me, muzzle, enemies)
        distance = math.dist(me["pos"], target["pos"]) if target else math.inf
        move = self.movement(obs, target)
        action = {
            "tick": obs["tick"], "move": move,
            "boost": me["grounded"] and not me["in_zone"],
            "jump": self.stalled_for >= 0.3 and me["grounded"],
        }
        if obs["offer"]:
            action["pick"] = 0
        if secondary is None:
            pickup = min(
                (p for p in obs["pickups"] if p["kind"] in ("lightning", "laser")
                 and math.dist((x, y), p["pos"][:2]) <= self.pickup_radius
                 and abs(p["pos"][2] - z) <= 4),
                key=lambda p: (p["kind"] != "lightning", math.dist((x, y), p["pos"][:2])),
                default=None,
            )
            if pickup:
                action["take"] = pickup["id"]

        gun_range = gun["stats"]["range"]
        if distance > gun_range and gun.get("ammo", 0) < gun["stats"]["mag"]:
            action["reload"] = True
        if target is None:
            if any(move):
                action["aim"] = (math.atan2(move[1], move[0]), 0.0)
            return action

        dx, dy, dz = (value - start for value, start in zip(target["pos"], muzzle))
        direct_yaw = math.atan2(dy, dx)
        direct_pitch = math.atan2(dz + 4.5, math.hypot(dx, dy))
        gun_yaw, gun_pitch = gun_aim(muzzle, target, gun["stats"]["speed"])
        aim_yaw, aim_pitch = gun_yaw, gun_pitch
        fire_secondary = False
        if secondary and secondary["kind"] == "lightning" and distance <= secondary["stats"]["range"]:
            fire_secondary = abs(math.remainder(direct_yaw - me["aim"][0], math.tau)) < math.radians(12)
        if secondary and secondary["kind"] == "laser":
            charge = secondary.get("charge", 0)
            if charge > 0 or (gun.get("ammo", 0) == 0 and secondary["cooldown"] <= 0
                              and distance <= secondary["stats"]["range"] and me["in_zone"]):
                aim_yaw, aim_pitch = direct_yaw, direct_pitch
                aligned = self.aligned(me["aim"], aim_yaw, aim_pitch, distance)
                fire_secondary = distance <= secondary["stats"]["range"] and (
                    charge < secondary["stats"]["charge"] or not aligned
                )

        action["aim"] = (aim_yaw, aim_pitch)
        action["fire"] = [
            distance <= gun_range and self.gun_trigger(me, target, muzzle, (gun_yaw, gun_pitch), action["aim"], distance),
            fire_secondary,
        ]
        return action

    def gun_trigger(self, me, target, muzzle, lead, command, distance):
        return self.aligned(me["aim"], *lead, distance)

    @staticmethod
    def aligned(actual, yaw, pitch, distance):
        tolerance = math.atan2(2.0, max(1.0, distance - 3.0))
        return (abs(math.remainder(yaw - actual[0], math.tau)) < tolerance
                and abs(pitch - actual[1]) < tolerance)


if __name__ == "__main__":
    mf.run(Bot)
