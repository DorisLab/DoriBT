"""Public API workloads; independent runs share immutable data, never an account."""

import hashlib
import json
import statistics
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import numpy as np
from market_case import moving_average, require_equal, result_digest

from doribt import (
    Backtest,
    BacktestResult,
    Context,
    Costs,
    Instrument,
    MarketData,
    RuleBook,
    RulePeriod,
    TradingRule,
)


def synthetic_market(days: int, assets: int) -> MarketData:
    if days < 60 or not 1 <= assets <= 100:
        raise ValueError("benchmark requires at least 60 sessions and 1..100 assets")
    sessions: list[date] = []
    current = date(2020, 1, 2)
    while len(sessions) < days:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    symbols = tuple(f"SYNTH{index:03}" for index in range(assets))
    rng = np.random.default_rng(20261006)
    paths = np.round(10 * np.exp(np.cumsum(rng.normal(0, 0.015, (days, assets)), axis=0)), 3)
    rule = TradingRule(
        price_tick=".001",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell=0,
        transfer_fee=0,
        instrument_kind="etf",
    )
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=symbol,
                start=sessions[0],
                end=sessions[-1],
                rule=rule,
                source="fictional benchmark ETF rules",
                version="1",
            )
            for symbol in symbols
        )
    )
    rows = [
        dict(
            session=session,
            symbol=symbol,
            status="trading",
            open=str(paths[i, j]),
            high=str(paths[i, j]),
            low=str(paths[i, j]),
            close=str(paths[i, j]),
            volume=1_000_000,
            upper_limit=None,
            lower_limit=None,
        )
        for i, session in enumerate(sessions)
        for j, symbol in enumerate(symbols)
    ]
    return MarketData.from_records(
        rows,
        calendar=sessions,
        instruments=[Instrument(symbol=s, kind="etf") for s in symbols],
        rules=rules,
        source="fictional benchmark paths/calendar; numpy seed 20261006; v1",
    )


def rotation(ctx: Context) -> None:
    if ctx.bar_index < 19 or (ctx.bar_index + 1) % 5:
        return
    scores = {}
    for symbol in ctx.symbols:
        prices = ctx.history(symbol, bars=20)
        scores[symbol] = float(prices[-1] / prices[0] - 1)
    selected = sorted(scores, key=lambda symbol: scores[symbol], reverse=True)[:5]
    # Equal weights truncated to the engine's explicit one-part-per-million precision.
    weight = (950000 // len(selected)) / 1_000_000
    ctx.target_weights(dict.fromkeys(selected, weight), rebalance=True)


def measured(callback: Callable[[], BacktestResult]) -> tuple[BacktestResult, float]:
    start = time.perf_counter()
    result = callback()
    return result, time.perf_counter() - start


def repeated(
    callback: Callable[[], BacktestResult], digest: str, repeats: int
) -> dict[str, object]:
    times = []
    for _ in range(repeats):
        result, elapsed = measured(callback)
        require_equal(result_digest(result), digest, "repeated run")
        times.append(elapsed)
    return {"seconds": times, "median_seconds": statistics.median(times)}


def single_case(data: MarketData, backend: str, repeats: int, parameters: int) -> dict[str, Any]:
    backtest = Backtest(data, costs=Costs(slippage_ticks=1))

    def run() -> BacktestResult:
        return backtest.run(moving_average, parameters={"fast": 20, "slow": 60}, backend=backend)

    first, elapsed = measured(run)
    digest = result_digest(first)
    warm = repeated(run, digest, repeats)
    grid = []
    durations = []
    for index in range(parameters):
        values = {"fast": 5 + index % 10 * 2, "slow": 40 + index // 10 * 5}

        def parameter_run(values: dict[str, int] = values) -> BacktestResult:
            return backtest.run(moving_average, parameters=values, backend=backend)

        result, duration = measured(parameter_run)
        durations.append(duration)
        grid.append({"parameters": values, "result_sha256": result_digest(result)})
    return {
        "first_run_seconds": elapsed,
        "warm": warm,
        "parameters": {"count": parameters, "run_seconds": sum(durations), "cases": grid},
        "result_sha256": digest,
        "fill_count": len(first.fills),
        "data_fingerprint": data.fingerprint,
        "sessions": len(data.sessions),
        "run_info": first.run_info.to_dict(),
    }


def portfolio_case(data: MarketData, backend: str, repeats: int) -> dict[str, Any]:
    backtest = Backtest(data, initial_cash=1_000_000, costs=Costs(slippage_ticks=1))

    def run() -> BacktestResult:
        return backtest.run(rotation, backend=backend)

    first, elapsed = measured(run)
    digest = result_digest(first)
    return {
        "first_run_seconds": elapsed,
        "warm": repeated(run, digest, repeats),
        "result_sha256": digest,
        "fill_count": len(first.fills),
        "data_fingerprint": data.fingerprint,
        "sessions": len(data.sessions),
        "assets": len(data.symbols),
    }


def verify_backends(reports: list[dict[str, Any]]) -> str:
    signatures = []
    for report in reports:
        single, portfolio = report["single"], report["portfolio"]
        values = {
            "single": single["result_sha256"],
            "single_data": single["data_fingerprint"],
            "parameters": single["parameters"]["cases"],
            "portfolio": portfolio["result_sha256"],
            "portfolio_data": portfolio["data_fingerprint"],
        }
        signatures.append(hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest())
    if len(signatures) < 2 or len(set(signatures)) != 1:
        raise AssertionError("benchmark backend/account result digests differ or are missing")
    return signatures[0]
