"""Unit tests for makefun_bars.py (stdlib unittest). They run only inside python:3.13-slim:
tests/unit/sdk-bars.test.ts executes ``python3 -P -s /sdk/test_makefun_bars.py`` with
``PYTHONHASHSEED=0``, as the grader runs a bot.
"""

import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import makefun_bars as sdk  # noqa: E402

USDC = 1_000_000
MINT_SOL = "So11111111111111111111111111111111111111112"
MINT_JUP = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"


def hello(**caps):
    return {
        "type": "hello",
        "protocol": sdk.PROTOCOL,
        "seed": "7",
        "symbols": [
            {"symbol": "JUP", "mint": MINT_JUP, "price_scale": 6, "qty_scale": 6},
            {"symbol": "SOL", "mint": MINT_SOL, "price_scale": 6, "qty_scale": 9},
        ],
        "capital": {"quote": "USDC", "quote_scale": 6, "quote_units": str(10_000 * USDC)},
        "bar_interval": "1h",
        "first_close_ms": 1_767_229_200_000,
        "caps": {"max_open_positions": 4, "max_orders_per_bar": 8, "max_weight_bps": 5_000, "shorts": False, "leverage": False, **caps},
        "fees": {"fee_bps": 30, "slippage_bps": 10, "min_notional_quote_units": str(USDC)},
        "latency_bars": 1,
    }


def bar(symbol, seq, close, c_depth=(5_000_000 * USDC,), o_depth=None):
    t = 1_767_229_200_000 + seq * 3_600_000
    c = str(close)
    return {
        "symbol": symbol,
        "t": t,
        "o": c,
        "h": c,
        "l": c,
        "c": c,
        "v": None,
        "o_depth": [str(d) for d in (c_depth if o_depth is None else o_depth)],
        "c_depth": [str(d) for d in c_depth],
    }


def account(cash=10_000 * USDC, positions=(), equity=None):
    return {
        "cash_quote_units": str(cash),
        "positions": [{"symbol": s, "qty": str(q), "cost_quote_units": str(c)} for s, q, c in positions],
        "equity_quote_units": str(cash if equity is None else equity),
    }


def batch(seq, bars=(), fills=(), acct=None):
    return {"type": "batch", "seq": seq, "t": 1_767_229_200_000 + seq * 3_600_000, "bars": list(bars), "fills": list(fills), "account": acct or account()}


def done(seq, acct=None):
    return {"type": "done", "seq": seq, "reason": "end_of_data", "account": acct or account()}


def lines(*msgs):
    return b"".join(json.dumps(m, separators=(",", ":")).encode() + b"\n" for m in msgs)


class Out(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


def run(on_batch, data, **kw):
    out = Out()
    result = sdk.run(on_batch, input=io.BytesIO(data), output=out, **kw)
    return result, out


class ReadLines(unittest.TestCase):
    def test_splits_lines_drops_cr_and_yields_an_unterminated_tail(self):
        self.assertEqual(list(sdk.read_lines(io.BytesIO(b"a\r\nb\n\nc"))), ["a", "b", "", "c"])

    def test_a_line_of_exactly_max_bytes_passes_and_one_more_byte_fails(self):
        self.assertEqual(list(sdk.read_lines(io.BytesIO(b"x" * 8 + b"\n"), 8)), ["x" * 8])
        for data in (b"x" * 9 + b"\n", b"x" * 9):
            with self.assertRaises(sdk.ProtocolError):
                list(sdk.read_lines(io.BytesIO(data), 8))

    def test_invalid_utf8_is_a_protocol_error(self):
        with self.assertRaises(sdk.ProtocolError):
            list(sdk.read_lines(io.BytesIO(b"\xff\n")))


class Run(unittest.TestCase):
    def test_one_flushed_reply_per_batch_echoing_seq_and_nothing_for_done(self):
        seen = []
        result, out = run(lambda s, b: seen.append(b["seq"]), lines(hello(), batch(0), batch(1), done(2)))
        self.assertEqual(out.getvalue(), '{"type":"reply","seq":0,"orders":[]}\n{"type":"reply","seq":1,"orders":[]}\n')
        self.assertEqual(out.flushes, 2)
        self.assertEqual(seen, [0, 1])
        self.assertEqual(result.batches, 2)
        self.assertEqual(result.done["seq"], 2)

    def test_stops_reading_at_done(self):
        src = io.BytesIO(lines(hello(), batch(0), done(1)) + b"not json\n")
        sdk.run(lambda s, b: [], input=src, output=Out())
        self.assertEqual(src.read(), b"not json\n")

    def test_amounts_become_decimal_strings_and_client_ids_are_filled_in(self):
        def on_batch(state, b):
            if b["seq"] == 0:
                return [
                    {"side": "buy", "symbol": "SOL", "notional_quote_units": 500 * USDC, "max_slippage_bps": 100},
                    {"side": "buy", "symbol": "JUP", "notional_quote_units": "250000000", "max_slippage_bps": 0, "client_id": "o2"},
                    {"side": "sell", "symbol": "SOL", "qty": 3, "max_slippage_bps": 10_000},
                ]
            return [{"side": "buy", "symbol": "JUP", "notional_quote_units": 1, "max_slippage_bps": 5}]

        _, out = run(on_batch, lines(hello(), batch(0), batch(1), done(2)))
        replies = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(
            replies[0]["orders"],
            [
                {"side": "buy", "client_id": "o1", "symbol": "SOL", "notional_quote_units": "500000000", "max_slippage_bps": 100},
                {"side": "buy", "client_id": "o2", "symbol": "JUP", "notional_quote_units": "250000000", "max_slippage_bps": 0},
                {"side": "sell", "client_id": "o3", "symbol": "SOL", "qty": "3", "max_slippage_bps": 10_000},
            ],
        )
        self.assertEqual(replies[1]["orders"][0]["client_id"], "o4")
        self.assertEqual(out.getvalue().splitlines()[1], sdk.encode_reply(1, replies[1]["orders"]))

    def test_state_follows_bars_and_the_account(self):
        states = []

        def on_batch(state, b):
            states.append((state.seq, state.t, state.cash, state.equity, state.close("SOL"), state.close("JUP"),
                           {k: (v.qty, v.cost) for k, v in state.positions.items()}, state.value("SOL", 2 * 10**9), state.weight_room("SOL")))

        held = account(cash=8_000 * USDC, positions=[("SOL", 10 * 10**9, 2_000 * USDC)], equity=9_500 * USDC)
        run(on_batch, lines(hello(), batch(0, [bar("SOL", 0, 150 * USDC)]), batch(1, [bar("JUP", 1, 800_000)], acct=held), done(2)))
        self.assertEqual(states[0], (0, 1_767_229_200_000, 10_000 * USDC, 10_000 * USDC, 150 * USDC, None, {}, 300 * USDC, 5_000 * USDC))
        # 50% of 9,500 USDC less 10 SOL at its latest close (150, from batch 0): 4,750 - 1,500.
        self.assertEqual(states[1], (1, 1_767_232_800_000, 8_000 * USDC, 9_500 * USDC, 150 * USDC, 800_000, {"SOL": (10 * 10**9, 2_000 * USDC)}, 300 * USDC, 3_250 * USDC))
        state = sdk.BarsState(hello(max_weight_bps=1_000))
        state.apply_batch(batch(0, [bar("SOL", 0, 150 * USDC)], acct=account(cash=0, positions=[("SOL", 10 * 10**9, 1)], equity=1_500 * USDC)))
        self.assertEqual(state.weight_room("SOL"), 0)
        self.assertEqual(state.value("BONK", 5), 0)

    def test_depth_at_is_the_latest_close_depth_and_impact_bps_what_a_trade_pays_on_it(self):
        state = sdk.BarsState(hello())
        self.assertIsNone(state.depth_at("SOL"))
        self.assertIsNone(state.impact_bps("SOL", 1_000 * USDC))
        # One pool 5,000,000 USDC deep at the close (its open was deeper): 1,000 USDC is 2 bps of it.
        state.apply_batch(batch(0, [bar("SOL", 0, 150 * USDC, (5_000_000 * USDC,), (6_000_000 * USDC,))]))
        self.assertEqual(state.depth_at("SOL"), [5_000_000 * USDC])
        self.assertEqual([state.impact_bps("SOL", 1_000 * USDC), state.impact_bps("SOL", 0), state.impact_bps("SOL", 2_499 * USDC)], [2, 0, 4])
        # A SOL-quoted asset crosses its pool and the SOL/USDC leg: 1,000 x (1/2,000,000 + 1/9,000,000) = 6.1 bps, 50,000 is 305.5.
        state.apply_batch(batch(1, [bar("JUP", 1, 800_000, (2_000_000 * USDC, 9_000_000 * USDC))]))
        self.assertEqual(state.depth_at("JUP"), [2_000_000 * USDC, 9_000_000 * USDC])
        self.assertEqual([state.impact_bps("JUP", 1_000 * USDC), state.impact_bps("JUP", 50_000 * USDC)], [6, 305])
        # A symbol keeps its latest bar's depth across a gap; one never sent has none.
        state.apply_batch(batch(2))
        self.assertEqual(state.depth_at("SOL"), [5_000_000 * USDC])
        self.assertIsNone(state.depth_at("BONK"))

    def test_orders_the_harness_would_refuse_raise_order_error_and_write_nothing(self):
        good = {"side": "buy", "symbol": "SOL", "notional_quote_units": 5, "max_slippage_bps": 5}
        bad = [
            "not a list",
            ["not an order"],
            [{**good, "side": "short"}],
            [{**good, "mint": MINT_SOL}],
            [{**good, "qty": 1}],
            [{"side": "sell", "symbol": "SOL", "qty": 1, "notional_quote_units": 1, "max_slippage_bps": 5}],
            [{**good, "symbol": "sol"}],
            [{**good, "symbol": "S" * 21}],
            [{**good, "notional_quote_units": -1}],
            [{**good, "notional_quote_units": "01"}],
            [{**good, "notional_quote_units": 2**64}],
            [{**good, "notional_quote_units": 1.0}],
            [{**good, "notional_quote_units": True}],
            [{**good, "max_slippage_bps": 10_001}],
            [{**good, "max_slippage_bps": True}],
            [{**good, "client_id": "_flatten_0"}],
            [{**good, "client_id": "x" * 65}],
            [{**good, "client_id": "a b"}],
            [good] * 9,
        ]
        for result in bad:
            with self.subTest(result=result if len(str(result)) < 120 else "9 orders"):
                out = Out()
                with self.assertRaises(sdk.OrderError):
                    sdk.run(lambda s, b, r=result: r, input=io.BytesIO(lines(hello(), batch(0), done(1))), output=out)
                self.assertEqual(out.getvalue(), "")

    def test_more_orders_than_max_orders_per_bar_names_both_numbers(self):
        order = {"side": "buy", "symbol": "SOL", "notional_quote_units": 5, "max_slippage_bps": 5}
        with self.assertRaisesRegex(sdk.OrderError, r"returned 3 orders, over hello\.caps\.max_orders_per_bar \(2\)"):
            run(lambda s, b: [order] * 3, lines(hello(max_orders_per_bar=2), batch(0), done(1)))
        _, out = run(lambda s, b: [order] * 2, lines(hello(max_orders_per_bar=2), batch(0), done(1)))
        self.assertEqual(len(json.loads(out.getvalue())["orders"]), 2)

    def test_a_reply_over_the_line_limit_raises_before_writing(self):
        orders = [{"side": "buy", "symbol": "SOL", "notional_quote_units": 5, "max_slippage_bps": 5, "client_id": f"{i:064d}"} for i in range(500)]
        out = Out()
        with self.assertRaisesRegex(sdk.OrderError, r"the reply is \d+ bytes \(max 65536\)"):
            sdk.run(lambda s, b: orders, input=io.BytesIO(lines(hello(max_orders_per_bar=500), batch(0), done(1))), output=out)
        self.assertEqual(out.getvalue(), "")

    def test_protocol_errors(self):
        cases = [
            lines({**hello(), "protocol": "agent-fun/replay/v2"}),
            lines(batch(0)),
            lines(done(0)),
            lines(hello(), hello()),
            lines(hello(), batch(1)),
            lines(hello(), batch(0), batch(0)),
            lines(hello(), batch(0), done(3)),
            lines(hello(), {"type": "mark"}),
            lines(hello(), {**batch(0), "bars": None}),
            lines(hello(), {**batch(0), "t": "0"}),
            lines(hello()) + b"{not json\n",
            lines(hello(), batch(0)),
            b"",
        ]
        for data in cases:
            with self.subTest(data=data[:80]):
                with self.assertRaises(sdk.ProtocolError):
                    run(lambda s, b: [], data)

    def test_blank_lines_between_messages_are_skipped(self):
        result, _ = run(lambda s, b: [], lines(hello()) + b"\n\r\n" + lines(batch(0), done(1)))
        self.assertEqual(result.batches, 1)

    def test_warm_up_accessors_read_zero_and_false_without_the_key(self):
        seen = []
        run(lambda s, b: seen.append((s.seq, s.warmup_bars, s.warming_up)), lines(hello(), batch(0), batch(1), done(2)))
        self.assertEqual(seen, [(0, 0, False), (1, 0, False)])
        state = sdk.BarsState(hello())
        self.assertEqual((state.warmup_bars, state.warming_up), (0, False))

    def test_warm_up_accessors_follow_hello_warmup_bars(self):
        seen = []
        warm = {**hello(), "warmup_bars": 2}
        run(lambda s, b: seen.append((s.seq, s.warmup_bars, s.warming_up)), lines(warm, batch(0), batch(1), batch(2), batch(3), done(4)))
        self.assertEqual(seen, [(0, 2, True), (1, 2, True), (2, 2, False), (3, 2, False)])

    def test_a_warmup_rejection_is_an_ordinary_fill_reason(self):
        self.assertEqual(sdk.REJECT_REASONS[-1], "warmup")
        rejected = {"client_id": "o1", "symbol": "SOL", "side": "buy", "status": "rejected", "reason": "warmup",
                    "decided_bar": 1_767_229_200_000, "fill_bar": 1_767_232_800_000, "price": "0", "qty": "0",
                    "notional_quote_units": "0", "fee_quote_units": "0"}
        result, _ = run(lambda s, b: [], lines({**hello(), "warmup_bars": 1}, batch(0), batch(1, fills=[rejected]), done(2)))
        self.assertEqual(result.batches, 2)
        self.assertEqual(result.state.cash, 10_000 * USDC)


if __name__ == "__main__":
    unittest.main()
