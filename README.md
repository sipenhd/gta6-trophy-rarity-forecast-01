# gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/sipenhd/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/sipenhd/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

How many GTA VI players will hold each of the 55 PS5 trophies a week after launch — forecast honestly, with a spread that admits what it doesn't know. make.fun bounty entry.

## Run it

```sh
python3 main.py
```

Reads every case in `$MAKEFUN_INPUT_DIR` (default `/input`), writes one `<id>.out` per case to `$MAKEFUN_OUTPUT_DIR` (default `/output`): five quantiles (5%, 25%, 50%, 75%, 95%) of each trophy's Exophase earn rate at the target. Standard library only, no network, deterministic.

## Method

Every trophy's earn rate is earners ÷ players-tracked, so the forecast is built in logit space from two views of the same history:

1. **Local trend** — a recency-weighted line of logit(rate) against ln(1 + hours since release) over the last 24 hours of reads, slope soft-shrunk by its own standard error and damped on extrapolation. An adoption curve is S-shaped, so a straight line only makes sense locally.
2. **Earners ÷ tracked** — earners and players-tracked extrapolated separately on the same log-time scale and divided again, which captures the dilution that hits every rate when a wave of new players joins and Exophase refreshes its counts.

The median blends the two; the quantile spread grows with the horizon (random-walk term) plus the fit's residual plus a refresh term. When the whole history is one flat page that never refreshed — the launch-night practice shape — the forecast expects Exophase's first refresh to drop every rate and widens the band instead of pretending nothing will move.

## Test scores (local, simulated)

- Practice cases, assuming the answer is the documented 04:30 refresh with earners held constant (players tracked 638 → 3,868): pinball loss **0.33**, vs the house baseline's **1.69**.
- A synthetic final-like case (two days of reads, 4.5-day horizon, saturating adoption): **0.24** vs baseline **0.28**.
- Deterministic: two runs write byte-identical outputs. Runtime ~0.06s per case.

---

<sub>Entered on [make.fun](https://make.fun/?ref=bjmj9zhr&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
