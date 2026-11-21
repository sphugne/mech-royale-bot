"""Test a gun trigger that accounts for target size and torso slew."""
import math

import mechfight as mf
from combat_bot import gun_aim
from rear_angle_bot import Bot as RearAngleBot


class Bot(RearAngleBot):
    name = "duel-py"

    def __init__(self, hello):
        super().__init__(hello)
        self.mech_config = hello["config"]["mech"]
        self.cube_size = hello["config"]["cubes"].get("size_per_cube", 0.05)

    def gun_trigger(self, me, target, muzzle, lead, command, distance):
        gun = me["weapons"][0]
        cooldown = gun["cooldown"]
        if gun.get("ammo", 0) <= 0 or gun.get("reload", 0) > 0 or cooldown > 0.1:
            return False

        stats = me["stats"]
        yaw, pitch = me["aim"]
        # If the gun is still cooling down on the first tick, the torso
        # has at least one tick to turn before a shot can leave.
        delay = 0.05 if cooldown > 0.05 else 0.0
        yaw_step = delay * stats.get("turn_rate", self.mech_config.get("turn_rate", 4))
        pitch_step = delay * stats.get("pitch_rate", self.mech_config.get("pitch_rate", 3))
        yaw_error = math.remainder(command[0] - yaw, math.tau)
        min_pitch = stats.get("min_pitch", self.mech_config.get("min_pitch", -0.7))
        max_pitch = stats.get("max_pitch", self.mech_config.get("max_pitch", 1.3))
        pitch_error = max(min_pitch, min(max_pitch, command[1])) - pitch
        yaw += max(-yaw_step, min(yaw_step, yaw_error))
        pitch += max(-pitch_step, min(pitch_step, pitch_error))

        scale = 1 + self.cube_size * target.get("cubes", 0)
        center_offset = self.mech_config.get("height", 9) / 2
        # gun_aim expects a target whose center is 4.5 m above pos.z.
        future = [position + delay * velocity for position, velocity in zip(target["pos"], target["vel"])]
        future[2] += center_offset * scale - 4.5
        launch = tuple(position + delay * velocity for position, velocity in zip(muzzle, me["vel"]))
        predicted = {**target, "pos": future}
        desired_yaw, desired_pitch = gun_aim(launch, predicted, gun["stats"]["speed"])

        travel = max(1, distance - 3)
        radius = self.mech_config.get("radius", 2.5) * scale
        yaw_limit = math.atan2(0.85 * radius, travel)
        pitch_limit = math.atan2(0.85 * center_offset * scale, travel)
        return (abs(math.remainder(desired_yaw - yaw, math.tau)) <= yaw_limit
                and abs(desired_pitch - pitch) <= pitch_limit)


if __name__ == "__main__":
    mf.run(Bot)
