"""Validate a user-supplied ordinary ETF CSV against an independent Decimal ledger.

Files must follow docs/data-contract.md. The separate calendar CSV has a session
column. This harness assumes no corporate actions in the supplied interval; it
does not infer missing actions or silently adjust prices. Do not publish data
without permission. It runs no network downloads or live trading operations.
"""

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from etf_reference import reference

from doribt import (
    Backtest,
    BacktestResult,
    Context,
    Costs,
    Instrument,
    MarketData,
    WeightTargets,
    china_rules,
)


def load_market(
    path: Path, calendar: Path, profile: str, source: str
) -> tuple[MarketData, list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with calendar.open(encoding="utf-8-sig", newline="") as stream:
        sessions = [row["session"] for row in csv.DictReader(stream)]
    symbols = {row["symbol"] for row in rows}
    if len(symbols) != 1 or not sessions:
        raise ValueError("case requires one ETF and a nonempty independent calendar")
    symbol = next(iter(symbols))
    if profile not in {"sse_equity_etf", "szse_equity_etf"}:
        raise ValueError("case requires an ordinary domestic equity ETF profile")
    data = MarketData.from_records(
        rows,
        calendar=sessions,
        instruments=[Instrument(symbol=symbol, kind="etf")],
        rules=china_rules({symbol: profile}, start=sessions[0], end=sessions[-1]),
        source=source,
    )
    return data, sorted(rows, key=lambda row: row["session"])


def close_weights(data: MarketData, fast: int, slow: int, *, hold: bool = False) -> list[float]:
    if not 1 <= fast < slow:
        raise ValueError("windows require 1 <= fast < slow")
    prices = data.prices("close")[:, 0]
    if hold:
        return [0.95] * len(prices)
    return [
        0.95
        if index + 1 >= slow
        and np.mean(prices[index + 1 - fast : index + 1])
        > np.mean(prices[index + 1 - slow : index + 1])
        else 0
        for index in range(len(prices))
    ]


def moving_average(ctx: Context, *, fast: int, slow: int) -> None:
    values = ctx.history(ctx.symbols[0], bars=slow)
    weight = 0.95 if len(values) == slow and np.mean(values[-fast:]) > np.mean(values) else 0
    ctx.target_weights({ctx.symbols[0]: weight})


def result_digest(result: BacktestResult) -> str:
    values = {
        "cash": result.cash_units.tolist(),
        "equity": result.equity_units.tolist(),
        "holdings": result.holdings.tolist(),
        "orders": [asdict(order) for order in result.orders],
    }
    return hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()


def require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"independent validation differs: {label}")


def check_scope(data: MarketData) -> None:
    if (
        data.actions
        or data.adjustments
        or len(data.instruments) != 1
        or data.instruments[0].kind != "etf"
    ):
        raise ValueError("validation case requires one ETF with no corporate actions")
    expected = (Decimal(".001"), 100, 100, 100, 100, 1, 0, 0, 1_000_000)
    for period in data.rules.periods:
        rule = period.rule
        actual = (
            rule.price_tick,
            rule.buy_minimum,
            rule.buy_step,
            rule.sell_minimum,
            rule.sell_step,
            rule.settlement_days,
            rule.stamp_duty_sell,
            rule.transfer_fee,
            rule.order_maximum,
        )
        if actual != expected:
            raise ValueError("validation case requires the documented ordinary equity ETF rules")


def validate(
    data: MarketData,
    rows: list[dict[str, str]],
    *,
    fast: int,
    slow: int,
    backend: str,
) -> dict[str, Any]:
    check_scope(data)
    costs = Costs(slippage_ticks=1)
    run = Backtest(data, initial_cash=100_000, costs=costs)
    results = {}
    for name, hold in (("buy_and_hold", True), ("moving_average", False)):
        weights = close_weights(data, fast, slow, hold=hold)
        result = run.run(
            WeightTargets(sessions=data.sessions, weights={data.symbols[0]: weights}),
            backend=backend,
        )
        expected = reference(rows, weights)
        require_equal(
            result.cash_units.tolist(), [int(value * 10000) for value in expected.cash], "cash"
        )
        require_equal(
            result.equity_units.tolist(),
            [int(value * 10000) for value in expected.equity],
            "equity",
        )
        require_equal(result.holdings[:, 0].tolist(), list(expected.holdings), "holdings")
        actual_fills = [
            (str(f.session), f.quantity, f.price_units, f.commission_units) for f in result.fills
        ]
        require_equal(
            actual_fills,
            [
                (session, quantity, int(price * 10000), int(fee * 10000))
                for session, quantity, price, fee in expected.fills
            ],
            "fills and fees",
        )
        actual_blocked = [
            (str(o.session), o.reason.value) for o in result.orders if o.reason.value != "none"
        ]
        require_equal(actual_blocked, list(expected.blocked), "blocked attempts")
        if not hold:
            callback = run.run(
                moving_average, parameters={"fast": fast, "slow": slow}, backend=backend
            )
            require_equal(result_digest(callback), result_digest(result), "callback/precomputed")
        results[name] = {
            "stats": result.stats(periods_per_year=252),
            "result_sha256": result_digest(result),
            "run_info": result.run_info.to_dict(),
            "reference": "exact Decimal equality",
        }
    return results


def write_report(path: Path, report: Mapping[str, object]) -> None:
    content = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    path = path.absolute()
    with tempfile.TemporaryDirectory(prefix=".validation-", dir=path.parent) as temporary:
        staged = Path(temporary) / "report.json"
        staged.write_text(content, encoding="utf-8")
        # Hard-link creation atomically refuses an existing destination on Windows/Linux.
        # Unsupported filesystems fail; no fallback to a clobbering rename or partial file.
        os.link(staged, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--profile", choices=["sse_equity_etf", "szse_equity_etf"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--no-corporate-actions",
        action="store_true",
        required=True,
        help="Confirm the data provider found no corporate actions in this interval",
    )
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data, rows = load_market(args.market, args.calendar, args.profile, args.source)
    cases = validate(data, rows, fast=args.fast, slow=args.slow, backend=args.backend)
    report = {
        "schema": "doribt.market-validation/1",
        "data_fingerprint": data.fingerprint,
        "market_csv_sha256": hashlib.sha256(args.market.read_bytes()).hexdigest(),
        "calendar_csv_sha256": hashlib.sha256(args.calendar.read_bytes()).hexdigest(),
        "sessions": len(data.sessions),
        "range": [str(data.sessions[0]), str(data.sessions[-1])],
        "cases": cases,
        "scope": "one T+1 equity ETF, no corporate actions, first close starts decisions",
    }
    write_report(args.output, report)
    for name, case in cases.items():
        print(name, case["stats"]["final_equity"], case["stats"]["fill_count"], case["reference"])


if __name__ == "__main__":
    main()
