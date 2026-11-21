# Mech Royale Bot

Python bot for the Builders Buildathon’s Mech Royale challenge.

The first experiment tests whether starting toward the next safe zone based on travel time and taking a short detour when stuck improves average placement. The bot keeps the starter’s targeting, firing, and weapon pickup rules.

`movement_bot.py` is the first experiment. It passed the conformance checker and scored 0.88 in practice.

`combat_bot.py` leads moving targets with the arm gun, strafes, and collects nearby cubes and compatible secondary weapons. It scored 1.60 in practice.

`cover_bot.py` uses the arena geometry to pick targets with a clear firing line and looks for nearby cover while reloading. It scored 1.90 in practice.

`evasion_bot.py` tests irregular strafing and movement in response to incoming projectiles and laser charges. It scored 1.96 in practice.

`isolation_bot.py` commits to exposed targets, seeks cover against multiple opponents, and closes into lightning range in isolated fights. `mechfight.py` handles the game protocol, and `Dockerfile` launches the isolation variant for the scorer.

The isolation variant uses the same urgency check for zone travel and dodging. A dodge must preserve urgent zone progress and avoid increasing predicted enemy exposure. During a gun reload, the bot keeps its planned shelter move unless lightning is ready and the target is already in range.

The corrected isolation bot passed all 300 observations locally and in Docker and scored 2.06 in practice.

`navigation_bot.py` resumes zone or cube travel when no opponent has a clear shot, while still checking whether to stay behind cover during a reload. Jump-and-jet recovery probes the direction that actually stalled and yields to a sharp dodge or detour. It rechecks the current zone edge and urgent progress toward the next circle before starting or continuing a climb. The Dockerfile launches this variant.
