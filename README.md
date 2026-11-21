# Mech Royale Bot

Python bot for the Builders Buildathon’s Mech Royale challenge.

The first experiment tests whether starting toward the next safe zone based on travel time and taking a short detour when stuck improves average placement. The bot keeps the starter’s targeting, firing, and weapon pickup rules.

`movement_bot.py` is the first experiment. It passed the conformance checker and scored 0.88 in practice.

`combat_bot.py` leads moving targets with the arm gun, strafes, and collects nearby cubes and compatible secondary weapons. It scored 1.60 in practice.

`cover_bot.py` builds on the combat bot. It uses the arena geometry to pick targets with a clear firing line and looks for nearby cover while reloading. `mechfight.py` handles the game protocol, and `Dockerfile` launches the cover variant for the scorer.
