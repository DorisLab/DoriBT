"""Immutable, identified market inputs for the baseline multi-asset engine."""

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .actions import CorporateAction
from .adjustments import PriceAdjustment, adjust, view_end
from .bars import Bar, calendar_days, parse_bar, validate_bar
from .instruments import Instrument, TradingStatus
from .rules import RuleBook
from .validation import DateLike, day


@dataclass(frozen=True)
class MarketData:
    """Date × security data; columns are securities sharing an account, not runs.

    Use from_records or from_csv to validate the complete input before execution.
    Calendar and historical rules must be supplied explicitly by the data provider.
    """

    sessions: tuple[date, ...]
    instruments: tuple[Instrument, ...]
    bars: tuple[Bar, ...]
    rules: RuleBook
    source: str
    actions: tuple[CorporateAction, ...] = ()
    adjustments: tuple[PriceAdjustment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", calendar_days(list(self.sessions)))
        object.__setattr__(self, "instruments", tuple(self.instruments))
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "actions", tuple(sorted(self.actions, key=lambda a: a.action_id)))
        object.__setattr__(
            self, "adjustments", tuple(sorted(self.adjustments, key=lambda a: a.action_id))
        )
        if not self.source.strip():
            raise ValueError("data source description is required")
        symbols = self.symbols
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("instruments must have unique, non-empty symbols")
        valid_days, valid_symbols = set(self.sessions), set(symbols)
        seen: set[tuple[date, str]] = set()
        for bar in self.bars:
            key = (bar.session, bar.symbol)
            if bar.session not in valid_days or bar.symbol not in valid_symbols or key in seen:
                raise ValueError(f"unexpected or duplicate bar: {key}")
            seen.add(key)
            if bar.status in (TradingStatus.TRADING, TradingStatus.SUSPENDED):
                validate_bar(bar, self.rules.at(bar.symbol, bar.session).rule)
        self._check_missing(seen)
        order = {symbol: index for index, symbol in enumerate(symbols)}
        object.__setattr__(
            self, "bars", tuple(sorted(self.bars, key=lambda b: (b.session, order[b.symbol])))
        )
        self._check_lifecycle()
        self._check_actions()
        self._check_rule_kinds()
        self._check_adjustments()

    def _check_rule_kinds(self) -> None:
        kinds = {instrument.symbol: instrument.kind for instrument in self.instruments}
        for period in self.rules.periods:
            expected = period.rule.instrument_kind
            if expected is not None and period.symbol in kinds and kinds[period.symbol] != expected:
                raise ValueError(f"rule instrument kind conflicts with {period.symbol}")

    def _check_missing(self, seen: set[tuple[date, str]]) -> None:
        missing = len(self.sessions) * len(self.instruments) - len(seen)
        if not missing:
            return
        first = next(
            (session, symbol)
            for session in self.sessions
            for symbol in self.symbols
            if (session, symbol) not in seen
        )
        raise ValueError(f"missing {missing} market rows; first: {first}")

    def _check_lifecycle(self) -> None:
        states: dict[str, TradingStatus] = {}
        for bar in self.bars:
            previous = states.get(bar.symbol, TradingStatus.UNLISTED)
            if previous == TradingStatus.DELISTED and bar.status != TradingStatus.DELISTED:
                raise ValueError(f"security reappears after delisting: {bar.symbol}")
            if previous != TradingStatus.UNLISTED and bar.status == TradingStatus.UNLISTED:
                raise ValueError(f"listed security becomes unlisted: {bar.symbol}")
            states[bar.symbol] = bar.status

    def _check_actions(self) -> None:
        ids = [action.action_id for action in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate corporate-action id")
        event_dates = [(action.symbol, day(action.ex_date)) for action in self.actions]
        if len(event_dates) != len(set(event_dates)):
            raise ValueError(
                "multiple corporate actions for one symbol/ex_date require a consolidated event"
            )
        for action in self.actions:
            if action.symbol not in self.symbols:
                raise ValueError(f"unknown corporate-action symbol: {action.symbol}")
            self._check_action_calendar(action)

    def _check_adjustments(self) -> None:
        ids = [item.action_id for item in self.adjustments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate price adjustment")
        actions = {item.action_id: item for item in self.actions}
        for item in self.adjustments:
            action = actions.get(item.action_id)
            if action is None:
                raise ValueError(f"price adjustment refers to unknown action: {item.action_id}")
            if day(item.known_on) < day(action.announced):
                raise ValueError(
                    f"price adjustment cannot be known before announcement: {item.action_id}"
                )

    def _check_action_calendar(self, action: CorporateAction) -> None:
        for name in ("record_date", "ex_date", "share_credit_date", "share_listing_date"):
            raw = getattr(action, name)
            if raw is None:
                continue
            session = day(raw)
            if self.sessions[0] <= session <= self.sessions[-1] and session not in self.sessions:
                raise ValueError(f"{name} must be a supplied trading session: {action.action_id}")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(instrument.symbol for instrument in self.instruments)

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, object]],
        *,
        calendar: Sequence[DateLike],
        instruments: Sequence[Instrument],
        rules: RuleBook,
        source: str,
        actions: Sequence[CorporateAction] = (),
        adjustments: Sequence[PriceAdjustment] = (),
    ) -> "MarketData":
        return cls(
            calendar_days(list(calendar)),
            tuple(instruments),
            tuple(map(parse_bar, records)),
            rules,
            source,
            tuple(actions),
            tuple(adjustments),
        )

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        calendar: Sequence[DateLike],
        instruments: Sequence[Instrument],
        rules: RuleBook,
        source: str,
        actions: Sequence[CorporateAction] = (),
        adjustments: Sequence[PriceAdjustment] = (),
    ) -> "MarketData":
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return cls.from_records(
                csv.DictReader(stream),
                calendar=calendar,
                instruments=instruments,
                rules=rules,
                source=source,
                actions=actions,
                adjustments=adjustments,
            )

    def prices(
        self, field: str, *, adjustment: str = "raw", as_of: DateLike | None = None
    ) -> NDArray[np.float64]:
        """Return a read-only yuan matrix ending at an optional explicit session."""
        if field not in {"open", "high", "low", "close"}:
            raise ValueError("price field must be open, high, low or close")
        end = view_end(self, adjustment, as_of)
        bars = self.bars[: end * len(self.instruments)]
        values = np.array([getattr(bar, field) / 10_000 if bar.close else np.nan for bar in bars])
        values = values.reshape(end, len(self.instruments))
        if adjustment == "asof":
            adjust(self, values, start=0, end=end, symbols=self.symbols)
        values.setflags(write=False)
        return values

    @property
    def fingerprint(self) -> str:
        payload = {
            "calendar": [d.isoformat() for d in self.sessions],
            "instruments": [asdict(i) for i in self.instruments],
            "bars": [asdict(b) for b in self.bars],
            "rules": [asdict(r) for r in self.rules.periods],
            "source": self.source,
            "actions": [asdict(action) for action in self.actions],
            "adjustments": [asdict(item) for item in self.adjustments],
        }
        encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
