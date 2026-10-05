"""DoriBT: A-share backtesting with explicit data, rules and accounting."""

from .actions import CorporateAction
from .data import MarketData
from .instruments import Instrument, TradingStatus
from .rules import RuleBook, RulePeriod, TradingRule

__all__ = [
    "CorporateAction",
    "Instrument",
    "MarketData",
    "RuleBook",
    "RulePeriod",
    "TradingRule",
    "TradingStatus",
]

__version__ = "0.1.0a1"
