"""Grid-search optimizer powered by BacktestEngine."""

from __future__ import annotations

import asyncio
import itertools
from copy import deepcopy
from typing import Any

from core.backtest_engine import BacktestEngine
from strategy.base_strategy import StrategySettings
from utils.logger import log


class StrategyOptimizer:
    """Runs asynchronous grid search over strategy parameter ranges."""

    def __init__(self, max_parallel_tasks: int = 4) -> None:
        self.max_parallel_tasks = max_parallel_tasks
        self.results: list[dict[str, Any]] = []

    async def run_grid_search(
        self,
        symbol: str,
        timeframe: str,
        date_range: tuple[str, str],
        parameter_ranges: dict[str, list[Any]],
        base_settings: StrategySettings,
    ) -> list[dict[str, Any]]:
        self.results = []
        start_date, end_date = date_range

        data_engine = BacktestEngine()
        dataframe = await data_engine.load_historical_data(symbol, timeframe, start_date, end_date)

        keys = list(parameter_ranges.keys())
        values = [parameter_ranges[k] for k in keys]
        combinations = [dict(zip(keys, combo, strict=False)) for combo in itertools.product(*values)]

        log(f"Optimizer started for {symbol}: {len(combinations)} combinations")
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)

        async def _run_combination(index: int, combo: dict[str, Any]) -> None:
            async with semaphore:
                result = await self.evaluate_combination(dataframe, base_settings, combo)
                result["index"] = index
                self.results.append(result)
                if index % 10 == 0:
                    log(f"Optimizer progress: {index}/{len(combinations)}")

        await asyncio.gather(*(_run_combination(idx + 1, combo) for idx, combo in enumerate(combinations)))
        self.rank_results()
        return self.results

    async def evaluate_combination(
        self,
        dataframe: Any,
        base_settings: StrategySettings,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        settings = deepcopy(base_settings)
        for key, value in params.items():
            setattr(settings, key, value)

        def _run() -> dict[str, Any]:
            engine = BacktestEngine()
            engine.dataframe = dataframe.copy()
            report = engine.run_backtest(settings)
            return {
                "params": params,
                "total_profit": float(report.get("total_profit", 0.0)),
                "win_rate": float(report.get("win_rate", 0.0)),
                "max_drawdown": float(report.get("max_drawdown", 0.0)),
                "profit_factor": float(report.get("profit_factor", 0.0)),
                "total_trades": int(report.get("total_trades", 0)),
            }

        return await asyncio.to_thread(_run)

    def rank_results(self) -> None:
        self.results.sort(
            key=lambda x: (
                -float(x["profit_factor"]),
                float(x["max_drawdown"]),
                -float(x["total_profit"]),
            )
        )

    def get_top_results(self, n: int = 10) -> list[dict[str, Any]]:
        if n <= 0:
            return []
        return self.results[:n]
