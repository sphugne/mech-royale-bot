"""Starter combat and pickups with timed zone movement and stall recovery."""
import math
import mechfight as mf


class Bot:
    name = "movement-py"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]

        self.last_position = None
        self.last_time = None
        self.last_move = (0.0, 0.0)
        self.stalled_for = 0.0
        self.detour_until = 0.0
        self.detour_side = -1

    def choose_move(self, obs: mf.Observation) -> tuple[float, float]:
        me = obs["self"]
        zone = obs["zone"]
        position = me["pos"][:2]
        now = obs["t"]
        dx = zone["next_center"][0] - position[0]
        dy = zone["next_center"][1] - position[1]
        distance = math.hypot(dx, dy)
        # Leave room for a building detour and stop a few meters inside.
        safe_radius = max(0.0, zone["next_radius"] - 5.0)
        remaining = max(0.0, distance - safe_radius)
        walk_speed = me["stats"]["walk_speed"]
        laser_charging = any(
            weapon and weapon["kind"] == "laser" and weapon.get("charge", 0) > 0
            for weapon in me["weapons"]
        )
        if laser_charging:
            walk_speed *= 0.5
        travel_time = remaining / max(walk_speed, 0.1)
        should_move = distance > 0.0 and (
            not me["in_zone"]
            or (remaining > 0.0 and now + 1.5 * travel_time + 5.0 >= zone["shrink_end"])
        )

        if should_move and self.last_position is not None and any(self.last_move):
            elapsed = now - self.last_time
            progress = sum(
                (current - previous) * direction
                for current, previous, direction in zip(position, self.last_position, self.last_move)
            )
            if me["grounded"] and 0 < elapsed <= 0.25 and progress < elapsed:
                self.stalled_for += elapsed
            else:
                self.stalled_for = 0.0
            if self.stalled_for >= 0.6 and now >= self.detour_until:
                self.detour_side *= -1
                self.detour_until = now + 1.5
                self.stalled_for = 0.0
        else:
            self.stalled_for = 0.0
            self.detour_until = 0.0

        move = (0.0, 0.0)
        if should_move:
            yaw = math.atan2(dy, dx)
            if now < self.detour_until:
                yaw += self.detour_side * math.pi / 2
            move = (math.cos(yaw), math.sin(yaw))

        self.last_position = position
        self.last_time = now
        self.last_move = move
        return move

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        goal = obs["zone"]["next_center"]
        act: mf.Action = {"tick": obs["tick"]}
        if obs["offer"]:
            act["pick"] = 0
        near = [p for p in obs["pickups"] if math.dist(p["pos"][:2], (x, y)) < self.reach]
        if me["weapons"][1] is None and near and near[0]["kind"] != "gun":
            act["take"] = near[0]["id"]
        enemies = sorted((m for m in obs["mechs"] if m["kind"] == "mech"), key=lambda m: math.dist(m["pos"], me["pos"]))
        yaw = math.atan2(goal[1] - y, goal[0] - x)
        act.update(move=list(self.choose_move(obs)), aim=[yaw, 0.0], boost=not me["in_zone"], jump=obs["tick"] % 40 == 0)
        if enemies:
            t = enemies[0]["pos"]
            aim = [math.atan2(t[1] - y, t[0] - x), math.atan2(t[2] - z - 2.5, math.dist(t[:2], (x, y)))]
            act.update(aim=aim, fire=[True, True])
            mf.draw.line([x, y, z + 7], [t[0], t[1], t[2] + 4.5], "#ff5040")
        mf.draw.point([goal[0], goal[1], z], "#40c0ff", 6)
        mf.draw.label(f"hp {me['hp']:.0f} · {len(enemies)} in sight")
        return act


mf.run(Bot)
