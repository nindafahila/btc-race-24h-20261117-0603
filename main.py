"""cbBTC range trader for make.fun btc-race-24h-20261117-0603 (bars-replay/v1).

Strategy: wide-band mean reversion around a 240-bar (4h) simple moving average,
with a two-leg exit that lets a strong rip run instead of banking it early,
and a stop that caps a dip-buy that keeps falling.
  - Buy (all-in, up to the weight cap) when the latest close is >= 0.8% below
    the 240-bar SMA: the dip is bought, not chased.
  - Once long, arm the exit when the close reaches 0.8% above the SMA, then
    sell the whole position when the rip either runs to 1.5% above the SMA
    (the cap: bank a strong swing near its top) or fades back to 0.3% above
    the SMA (the fade: a weak swing still exits in profit instead of being
    held to the end of the window). The exit is a state machine: _armed is
    set only while a position is held and cleared on a sell or when flat,
    so a position whose rip never reaches the arm level is simply held.
  - Stop: while long, sell at once if the close falls 0.8% below the entry
    close. A dip-buy is a bet the dip is the bottom; if the price keeps
    falling past the entry by that much, the bet was wrong and the loss is
    capped at roughly the stop plus one round trip of costs, instead of
    riding the position to the final flatten.
  - Otherwise hold whatever we hold (long or cash). No other trades.

Why this shape: on the 24h dev window cbBTC trades in a ~2.8% range with no
trend (open $64,461 -> close $64,776, +0.49%). Every round trip costs
~6 bps fee+slippage plus ~13 bps of pool impact at full size, so anything
that trades often loses money to fees; a 0.8% band means only a few trades,
each capturing a real swing. The old fixed exit (sell at +0.8% above the SMA)
banked the first rip at seq 509 while it kept running to +1.76% above the SMA
at seq 514; the two-leg exit sells that rip at the cap instead. Backtested
offline on the kit's dev bars with the harness fill model (fill at next
bar's open, 4 bps fee, 2 bps slippage, constant-product impact vs the fill
bar's o_depth), replayed through the protocol runner (replay.py):
  SMA 120/180/240/300/360 all score +$16.37..+$19.16 on the dev window
  (3 trades, max drawdown ~0.8%), vs +$9.79..+$10.81 for the fixed +0.8%
  exit (SMA 180/240/300). The fade leg alone (cap disabled) still scores
  +$6.97, so a window whose rip never reaches the cap degrades to a smaller
  profit, not a loss. The stop never fires on the dev window (lowest close
  after an entry is 0.36% below it), so it changes nothing there and only
  bounds the loss on a window where a dip keeps falling. Buy-and-hold
  scores +$2.78; every EMA-crossover / Bollinger / RSI / confirmation /
  trailing-stop variant tested scores negative or worse than the fixed exit.
  The band and the two-leg exit, not the exact SMA length, are what matter,
  so the choice is robust rather than fitted to one parameter. The cap level
  (+1.5%) is set from the dev window's observed rip (+1.76% peak); on a
  window with a weaker rip the fade leg does the selling instead.

Determinism: pure function of the closes seen so far (integer prices, float
SMA, two small state flags); no clock, no environment, no randomness, no
network, no files. During warm-up batches it only records history and
returns no orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 240          # bars of the SMA (4 hours of 1-minute bars)
BAND_BPS = 80           # 0.8% below the SMA to buy the dip
ARM_BPS = 80            # arm the exit once the close is this far above the SMA
FADE_BPS = 30           # sell once the rip fades back to this far above the SMA
CAP_BPS = 150           # ...or sell at once once it runs this far above the SMA
STOP_BPS = 80           # sell if the close falls this far below the entry close
MAX_SLIPPAGE_BPS = 100  # 1%: fills move ~2 bps slippage + ~13 bps impact at full size

_closes = []   # latest closes, in order (ints, price_scale 5)
_last_t = None
_armed = False  # True once the current position's rip has reached ARM_BPS
_entry = None   # entry close of the current position (ints, price_scale 5)


def _above(close, sma, bps):
    """True when close sits at least bps basis points above sma (exact ints)."""
    return close * 10000 >= sma * (10000 + bps)


def _below(close, sma, bps):
    """True when close sits at least bps basis points below sma (exact ints)."""
    return close * 10000 <= sma * (10000 - bps)


def on_batch(state, batch):
    global _last_t, _armed, _entry
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
    if held_qty == 0:
        _armed = False
        _entry = None
        if _below(close, sma, BAND_BPS):
            # Dip: buy up to the weight cap with all available cash.
            spend = min(state.cash, state.weight_room(SYMBOL))
            if spend >= min_notional and spend > 0:
                _entry = close
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": spend,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    # Stop: the dip kept falling past the entry; cap the loss.
    if _entry is not None and close * 10000 <= _entry * (10000 - STOP_BPS):
        _armed = False
        _entry = None
        return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    # Holding: arm the exit once the rip reaches ARM_BPS, then sell when it
    # either runs to CAP_BPS or fades back to FADE_BPS. Letting the rip run
    # banks more of a strong swing; the fade leg is the fallback when the
    # rip never reaches the cap, so a weak swing still exits in profit.
    if _above(close, sma, ARM_BPS):
        _armed = True
    if _armed and (_above(close, sma, CAP_BPS) or not _above(close, sma, FADE_BPS)):
        _armed = False
        _entry = None
        return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
