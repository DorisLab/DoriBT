"""DoriBT: A-share backtesting with explicit data, rules and accounting."""

from doribt.accounting.costs import Costs
from doribt.accounting.orders import Fill, IntentRecord, Order, Reason
from doribt.accounting.rights import CorporateEvent, EntitlementRecord, UnsupportedCorporateAction
from doribt.accounting.taxes import TaxLotRecord, TaxPayment, TaxRecord
from doribt.market.actions import CorporateAction
from doribt.market.adjustments import PriceAdjustment
from doribt.market.china import china_rules
from doribt.market.data import MarketData
from doribt.market.instruments import Instrument, TradingStatus
from doribt.market.rules import RuleBook, RulePeriod, TradingRule
from doribt.provenance import RunInfo
from doribt.reporting.benchmark import Benchmark
from doribt.reporting.report import ResearchReport
from doribt.reporting.result import BacktestResult
from doribt.research.config import RunConfig
from doribt.research.outputs import Metric, ResearchOutput, Series, Table
from doribt.research.parameters import Parameter, ParameterSet
from doribt.runtime.context import Context
from doribt.runtime.engine import Backtest
from doribt.runtime.slippage import BarExecution, FixedBps, FixedTicks, VolumeImpact
from doribt.runtime.targets import PositionTargets, WeightTargets

__all__ = [
    "RunConfig",
    "Parameter",
    "ParameterSet",
    "Metric",
    "Series",
    "Table",
    "ResearchOutput",
    "ResearchReport",
    "Backtest",
    "BarExecution",
    "FixedBps",
    "FixedTicks",
    "VolumeImpact",
    "BacktestResult",
    "Benchmark",
    "RunInfo",
    "Context",
    "Costs",
    "WeightTargets",
    "PositionTargets",
    "CorporateAction",
    "PriceAdjustment",
    "china_rules",
    "CorporateEvent",
    "EntitlementRecord",
    "UnsupportedCorporateAction",
    "TaxLotRecord",
    "TaxPayment",
    "TaxRecord",
    "Instrument",
    "MarketData",
    "RuleBook",
    "RulePeriod",
    "TradingRule",
    "TradingStatus",
    "Order",
    "Fill",
    "IntentRecord",
    "Reason",
]

__version__ = "0.2.0.dev0"
