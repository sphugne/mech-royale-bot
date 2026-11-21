# Mech Royale Bot

Python bot for the Builders Buildathon’s Mech Royale challenge.

The first experiment tests whether starting toward the next safe zone based on travel time and taking a short detour when stuck improves average placement. The bot keeps the starter’s targeting, firing, and weapon pickup rules.

`movement_bot.py` contains the bot, `mechfight.py` handles the game protocol, and `Dockerfile` launches the bot for the scorer. The movement variant passed all 300 observations in the official conformance checker, both locally and in Docker under the match limits.
