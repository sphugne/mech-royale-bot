"""Use the arena's solid geometry to choose shots and reload positions."""
import json
import math
from array import array
from pathlib import Path
from sys import byteorder

import mechfight as mf
from combat_bot import Bot as CombatBot, direction


def polygon_contains(points, x, y):
    inside = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > y) != (by > y) and x < ax + (bx - ax) * (y - ay) / (by - ay):
            inside = not inside
    return inside


class Prism:
    def __init__(self, data):
        self.base = data["base"]
        self.top = data["top"]
        self.rings = [list(zip(ring[::2], ring[1::2])) for ring in [data["ring"], *data["holes"]]]
        xs, ys = zip(*self.rings[0])
        self.bounds = min(xs), min(ys), max(xs), max(ys)

    def blocks(self, start, end):
        x, y, z = start
        ex, ey, ez = end
        left, bottom, right, top = self.bounds
        if (max(x, ex) < left or min(x, ex) > right or max(y, ey) < bottom
                or min(y, ey) > top or max(z, ez) < self.base or min(z, ez) > self.top):
            return False
        dx, dy, dz = ex - x, ey - y, ez - z
        lo, hi = 0.0, 1.0
        if dz:
            heights = sorted(((self.base - z) / dz, (self.top - z) / dz))
            lo, hi = max(lo, heights[0]), min(hi, heights[1])
        if lo > hi:
            return False

        # Between footprint edge crossings, the segment stays in the same region.
        cuts = [lo, hi]
        for ring in self.rings:
            for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
                sx, sy = bx - ax, by - ay
                cross = dx * sy - dy * sx
                if abs(cross) < 1e-9:
                    continue
                t = ((ax - x) * sy - (ay - y) * sx) / cross
                u = ((ax - x) * dy - (ay - y) * dx) / cross
                if lo < t < hi and 0 <= u <= 1:
                    cuts.append(t)
        cuts.sort()
        for a, b in zip(cuts, cuts[1:]):
            t = (a + b) / 2
            px, py = x + dx * t, y + dy * t
            if polygon_contains(self.rings[0], px, py) and not any(
                polygon_contains(hole, px, py) for hole in self.rings[1:]
            ):
                return True
        return False


class Arena:
    def __init__(self, directory):
        directory = Path(directory) / "v2"
        world = json.loads((directory / "world.json").read_text())
        self.prisms = [Prism(prism) for prism in world["prisms"]]
        self.grid = world["terrain"]
        self.heights = array("h")
        self.heights.frombytes((directory / self.grid["file"]).read_bytes())
        if byteorder != "little":
            self.heights.byteswap()

    def height(self, x, y):
        grid = self.grid
        nx, ny = grid["nx"], grid["ny"]
        gx = min(nx - 1, max(0, (x - grid["minX"]) / grid["step"]))
        gy = min(ny - 1, max(0, (y - grid["minY"]) / grid["step"]))
        i, j = min(int(gx), nx - 2), min(int(gy), ny - 2)
        fx, fy = gx - i, gy - j
        k = j * nx + i
        low = self.heights[k] * (1 - fx) + self.heights[k + 1] * fx
        high = self.heights[k + nx] * (1 - fx) + self.heights[k + nx + 1] * fx
        return (low * (1 - fy) + high * fy) * grid["scale"]

    def blocked(self, start, end):
        if any(prism.blocks(start, end) for prism in self.prisms):
            return True
        x, y, z = start
        dx, dy, dz = (target - source for source, target in zip(start, end))
        samples = max(1, math.ceil(math.hypot(dx, dy) / 2))
        for index in range(1, samples):
            t = index / samples
            if self.height(x + t * dx, y + t * dy) >= z + t * dz:
                return True
        return False


class Bot(CombatBot):
    name = "cover-py"
    protect_zone_progress = False

    def __init__(self, hello):
        super().__init__(hello)
        self.arena = Arena(hello["map"]["dir"])
        self.clear_shot = False

    def select_target(self, me, muzzle, enemies):
        ordered = sorted(enemies, key=lambda enemy: math.dist(me["pos"], enemy["pos"]))
        self.clear_shot = False
        for enemy in ordered[:4]:
            x, y, z = enemy["pos"]
            if not self.arena.blocked(muzzle, (x, y, z + 4.5)):
                self.clear_shot = True
                return enemy
        return ordered[0] if ordered else None

    def movement(self, obs, target):
        move = super().movement(obs, target)
        if self.protect_zone_progress and self.zone_urgent(obs):
            return move
        me, zone = obs["self"], obs["zone"]
        gun = me["weapons"][0]
        if not (target and gun.get("reload", 0) > 0 and me["grounded"] and me["in_zone"]):
            return move
        x, y, z = me["pos"]
        ex, ey, ez = target["pos"]
        enemy_muzzle = (ex, ey, ez + 7)
        if self.arena.blocked(enemy_muzzle, (x, y, z + 4.5)):
            if math.dist((x, y), zone["next_center"]) <= max(0, zone["next_radius"] - 8):
                self.last_move = (0.0, 0.0)
                return self.last_move
            return move

        dx, dy = direction(ex - x, ey - y)
        for step in ((-dy, dx), (dy, -dx), (-dx, -dy)):
            px, py = x + 7 * step[0], y + 7 * step[1]
            if (math.dist((px, py), zone["center"]) > zone["radius"] - 3
                    or math.dist((px, py), zone["next_center"]) > zone["next_radius"] - 8):
                continue
            ground = self.arena.height(px, py)
            if abs(ground - z) > 1.2 or self.arena.blocked((x, y, z + 1), (px, py, ground + 1)):
                continue
            if self.arena.blocked(enemy_muzzle, (px, py, ground + 4.5)):
                self.last_move = step
                return step
        return move

    def act(self, obs):
        action = super().act(obs)
        if not self.clear_shot:
            action.pop("fire", None)
        return action


if __name__ == "__main__":
    mf.run(Bot)
