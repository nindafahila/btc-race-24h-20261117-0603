# btc-race-24h-20261117-0603

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/nindafahila/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/nindafahila/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A cbBTC range-trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty: it trades Coinbase Wrapped BTC against USDC, minute by minute, on 1-minute on-chain prices with $1,000 of paper money. Wide-band mean reversion around a 240-bar (4-hour) moving average — buy at least 0.8% below the average, sell at least 0.8% above it, otherwise hold. On the published 24h dev window it scores +$10.81 net PnL after every fee, slippage and pool impact (3 trades, max drawdown ~0.7%), passing the dev gate.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout: one JSON line per minute bar in, one reply per batch out. No network, no clock, no randomness — a pure function of the closes seen so far, so two runs on the same data produce the same orders.

---

<sub>Entered on [make.fun](https://make.fun/?ref=xqemgw87&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
