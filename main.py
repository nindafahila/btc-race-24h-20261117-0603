"""cbBTC range trader for make.fun btc-race-24h-20261117-0603 (bars-replay/v1).

Strategy: wide-band mean reversion around a 240-bar (4h) simple moving average.
  - Buy (all-in, up to the weight cap) when the latest close is >= 0.8% below
    the 240-bar SMA: the dip is bought, not chased.
  - Sell the whole position when the latest close is >= 0.8% above the SMA:
    the rip is banked.
  - Otherwise hold whatever we hold (long or cash). No other trades.

Why this shape: on the 24h dev window cbBTC trades in a ~2.8% range with no
trend (open $64,461 -> close $64,776, +0.49%). Every round trip costs
~6 bps fee+slippage plus ~13 bps of pool impact at full size, so anything
that trades often loses money to fees; a 0.8% band means only a few trades,
each capturing a real swing. Backtested offline on the kit's dev bars with the
harness fill model (fill at next bar's open, 4 bps fee, 2 bps slippage,
constant-product impact vs the fill bar's o_depth):
  SMA 120/180/240/300/360 x 0.8% band all score +$11.50..+$12.55 on the dev
  window (3 trades, max drawdown ~0.7%); 0.6% and 0.7% bands also positive.
  Buy-and-hold scores +$2.78, every EMA-crossover / Bollinger / RSI variant
  tested scores negative. The band, not the exact SMA length, is what matters,
  so the choice is robust rather than fitted to one parameter.

Determinism: pure function of the closes seen so far (integer prices, float
SMA); no clock, no environment, no randomness, no network, no files.
During warm-up batches it only records history and returns no orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 240          # bars of the SMA (4 hours of 1-minute bars)
BAND_BPS = 80           # 0.8% below/above the SMA
MAX_SLIPPAGE_BPS = 100  # 1%: fills move ~2 bps slippage + ~13 bps impact at full size

_closes = []   # latest closes, in order (ints, price_scale 5)
_last_t = None


def on_batch(state, batch):
    global _last_t
    bar = state.latest.get(SYMBOL)
    if bar is not None and bar["t"] != _last_t:
        _closes.append(int(bar["c"]))
        _last_t = bar["t"]
    if state.warming_up:
        return []
    if len(_closes) < LOOKBACK:
        return []
    sma = sum(_closes[-LOOKBACK:]) / LOOKBACK
    close = _closes[-1]
    held = state.positions.get(SYMBOL)
    held_qty = held.qty if held is not None else 0
    min_notional = int(state.hello["fees"]["min_notional_quote_units"])
    if close * 10000 <= sma * (10000 - BAND_BPS):
        # Dip: buy up to the weight cap with all available cash.
        spend = min(state.cash, state.weight_room(SYMBOL))
        if spend >= min_notional and spend > 0:
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": spend,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if close * 10000 >= sma * (10000 + BAND_BPS):
        # Rip: sell the whole position.
        if held_qty > 0:
            return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    return []


makefun_bars.run(on_batch)
