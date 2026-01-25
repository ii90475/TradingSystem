"""Base class for trading strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType


@dataclass
class IndicatorConfig:
    """Configuration for a required indicator."""

    indicator_type: str
    params: dict[str, Any] = field(default_factory=dict)
    column_name: str | None = None  # Optional custom column name


@dataclass
class StrategyContext:
    """Context passed to strategy for signal generation."""

    instrument: str
    period: str
    candles: pd.DataFrame
    indicators: dict[str, pd.Series | pd.DataFrame]
    current_time: datetime
    current_price: float


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    To create a custom strategy:
    1. Subclass BaseStrategy
    2. Set name, description, instruments, periods
    3. Define required_indicators
    4. Implement generate_signals() method
    5. Place in strategies/examples/ or user strategies directory

    Example:
        class MyStrategy(BaseStrategy):
            name = "My Strategy"
            description = "A simple example strategy"
            version = "1.0.0"
            instruments = ["EUR_USD", "GBP_USD"]
            periods = ["M1", "M5"]
            required_indicators = [
                IndicatorConfig("sma", {"length": 20}),
                IndicatorConfig("rsi", {"length": 14}),
            ]

            def generate_signals(self, context: StrategyContext) -> list[Signal]:
                # Your signal logic here
                return []
    """

    # Strategy metadata
    name: str = "Base Strategy"
    description: str = ""
    version: str = "1.0.0"
    author: str = ""

    # Trading configuration
    instruments: list[str] = []
    periods: list[str] = []

    # Required indicators for this strategy
    required_indicators: list[IndicatorConfig] = []

    # Strategy parameters (can be overridden at runtime)
    default_params: dict[str, Any] = {}

    def __init__(self, **params: Any):
        """Initialize strategy with optional parameter overrides."""
        self.params = {**self.default_params, **params}
        self._is_running = False
        self._last_signal_time: datetime | None = None

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate trading signals based on current market data.

        This is the core method that each strategy must implement.
        It receives the current market context (candles + indicators)
        and returns a list of trading signals.

        Args:
            context: StrategyContext with candles, indicators, and metadata

        Returns:
            List of Signal objects (can be empty if no signals)
        """
        pass

    def on_start(self) -> None:
        """Called when strategy is started. Override for custom setup."""
        self._is_running = True

    def on_stop(self) -> None:
        """Called when strategy is stopped. Override for custom cleanup."""
        self._is_running = False

    def on_signal(self, signal: Signal) -> dict[str, Any] | None:
        """
        Called when a signal is generated. Override for custom handling.

        Can be used to transform signals into orders or perform
        additional validation before the signal is processed.

        Args:
            signal: The generated signal

        Returns:
            Optional dict with order parameters, or None to skip
        """
        return None

    def validate(self) -> list[str]:
        """
        Validate strategy configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.name:
            errors.append("Strategy name is required")

        if not self.instruments:
            errors.append("At least one instrument is required")

        if not self.periods:
            errors.append("At least one period is required")

        return errors

    @property
    def is_running(self) -> bool:
        """Check if strategy is currently running."""
        return self._is_running

    def get_info(self) -> dict[str, Any]:
        """Get strategy information as a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "instruments": self.instruments,
            "periods": self.periods,
            "required_indicators": [
                {
                    "type": ind.indicator_type,
                    "params": ind.params,
                    "column_name": ind.column_name,
                }
                for ind in self.required_indicators
            ],
            "default_params": self.default_params,
            "is_running": self._is_running,
        }

    def create_signal(
        self,
        signal_type: SignalType,
        instrument: str,
        strength: float = 1.0,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """
        Helper method to create a signal with strategy metadata.

        Args:
            signal_type: BUY, SELL, or HOLD
            instrument: Currency pair
            strength: Signal strength (0.0 to 1.0)
            reason: Human-readable reason for the signal
            metadata: Additional signal metadata

        Returns:
            Signal object ready for processing
        """
        from datetime import timezone

        now = datetime.now(timezone.utc)
        self._last_signal_time = now

        return Signal(
            time=now,
            strategy_id=self.name,
            instrument=instrument,
            signal_type=signal_type,
            strength=min(1.0, max(0.0, strength)),  # Clamp to 0-1
            reason=reason,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', running={self._is_running})"
