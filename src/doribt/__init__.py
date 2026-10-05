"""DoriBT: A-share backtesting with explicit data, rules and accounting."""

from .actions import CorporateAction
from .adjustments import PriceAdjustment
from .benchmark import Benchmark
from .china import china_rules
from .context import Context
from .costs import Costs
from .data import MarketData
from .engine import Backtest
from .instruments import Instrument, TradingStatus
from .orders import Fill, IntentRecord, Order, Reason
from .provenance import RunInfo
from .result import BacktestResult
from .rights import CorporateEvent, EntitlementRecord, UnsupportedCorporateAction
from .rules import RuleBook, RulePeriod, TradingRule
from .targets import WeightTargets
from .taxes import TaxLotRecord, TaxPayment, TaxRecord

__all__ = [
    "Backtest",
    "BacktestResult",
    "Benchmark",
    "RunInfo",
    "Context",
    "Costs",
    "WeightTargets",
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

__version__ = "0.1.0a1"
