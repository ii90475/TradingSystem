"""ATR Trailing Stop Strategy.

An exit management/trend following strategy that uses ATR-based
trailing stops that adjust with volatility.

Entry: EMA crossover (simple trend entry)
Exit: ATR-based trailing stop that adjusts with volatility
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Any

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@dataclass
class PositionState:
    """Tracks position state for trailing stop."""
    direction: str  # "long" or "short"
    entry_price: float
    stop_loss: float
    highest_price: float = 0.0  # For long positions
    lowest_price: float = float("inf")  # For short positions


@StrategyRegistry.register("atr_trailing")
class ATRTrailingStrategy(BaseStrategy):
    """
    ATR Trailing Stop Strategy.

    Uses EMA crossover for entries and ATR-based trailing stops for exits.
    Tracks position state to update stop losses based on price movement.

    Parameters:
        ema_fast: Fast EMA for entry (default: 10)
        ema_slow: Slow EMA for entry (default: 20)
        atr_period: ATR calculation period (default: 14)
        atr_multiplier: ATR multiplier for stop distance (default: 2.0)
    """

    name = "ATR Trailing Stop"
    description = "Trend following with ATR-based trailing stop exits"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M15", "1h", "4h"]

    default_params = {
        "ema_fast": 10,
        "ema_slow": 20,
        "atr_period": 14,
        "atr_multiplier": 2.0,
    }

    def __init__(self, **params: Any):
        """Initialize strategy with position tracking."""
        super().__init__(**params)
        self._position_state: dict[str, PositionState] = {}  # instrument -> state

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        ema_fast = self.params.get("ema_fast", 10)
        ema_slow = self.params.get("ema_slow", 20)
        atr_period = self.params.get("atr_period", 14)

        return [
            IndicatorConfig(
                indicator_type="ema",
                params={"length": ema_fast},
                column_name="ema_fast",
            ),
            IndicatorConfig(
                indicator_type="ema",
                params={"length": ema_slow},
                column_name="ema_slow",
            ),
            IndicatorConfig(
                indicator_type="atr",
                params={"length": atr_period},
                column_name="atr",
            ),
        ]

    def _calculate_stop_loss(self, price: float, atr: float, direction: str) -> float:
        """Calculate stop loss based on ATR."""
        multiplier = self.params.get("atr_multiplier", 2.0)
        stop_distance = atr * multiplier

        if direction == "long":
            return price - stop_distance
        else:  # short
            return price + stop_distance

    def _update_trailing_stop(self, state: PositionState, current_price: float, atr: float) -> float:
        """Update trailing stop based on price movement."""
        multiplier = self.params.get("atr_multiplier", 2.0)
        stop_distance = atr * multiplier

        if state.direction == "long":
            # Track highest price for long position
            if current_price > state.highest_price:
                state.highest_price = current_price
                # Move stop up
                new_stop = current_price - stop_distance
                if new_stop > state.stop_loss:
                    state.stop_loss = new_stop
        else:  # short
            # Track lowest price for short position
            if current_price < state.lowest_price:
                state.lowest_price = current_price
                # Move stop down
                new_stop = current_price + stop_distance
                if new_stop < state.stop_loss:
                    state.stop_loss = new_stop

        return state.stop_loss

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate ATR trailing stop signals.

        Handles both entries (EMA crossover) and exits (trailing stop hit).
        """
        signals = []

        # Get indicator values
        ema_fast = context.indicators.get("ema_fast")
        ema_slow = context.indicators.get("ema_slow")
        atr = context.indicators.get("atr")

        if ema_fast is None or ema_slow is None or atr is None:
            return signals

        # Need at least 2 data points
        if len(ema_fast) < 2 or len(ema_slow) < 2 or len(atr) < 1:
            return signals

        # Get current values
        fast_current = ema_fast.iloc[-1]
        fast_prev = ema_fast.iloc[-2]
        slow_current = ema_slow.iloc[-1]
        slow_prev = ema_slow.iloc[-2]
        atr_current = atr.iloc[-1]
        current_price = context.current_price

        if pd.isna(fast_current) or pd.isna(fast_prev) or pd.isna(slow_current) or pd.isna(slow_prev):
            return signals
        if pd.isna(atr_current):
            return signals

        instrument = context.instrument
        position = self._position_state.get(instrument)

        # Check for exit signals first (if we have a position)
        if position is not None:
            # Update trailing stop
            stop_loss = self._update_trailing_stop(position, current_price, atr_current)

            # Check if stop hit
            stop_hit = False
            if position.direction == "long" and current_price <= stop_loss:
                stop_hit = True
                exit_type = SignalType.SELL
                reason = f"ATR trailing stop hit at {stop_loss:.5f} (long exit)"
            elif position.direction == "short" and current_price >= stop_loss:
                stop_hit = True
                exit_type = SignalType.BUY
                reason = f"ATR trailing stop hit at {stop_loss:.5f} (short exit)"

            if stop_hit:
                # Calculate P&L for metadata
                if position.direction == "long":
                    pnl_pct = (current_price - position.entry_price) / position.entry_price
                else:
                    pnl_pct = (position.entry_price - current_price) / position.entry_price

                signals.append(self.create_signal(
                    signal_type=exit_type,
                    instrument=instrument,
                    strength=0.9,  # High strength for stop exits
                    reason=reason,
                    metadata={
                        "signal_category": "exit",
                        "exit_type": "trailing_stop",
                        "entry_price": float(position.entry_price),
                        "exit_price": float(current_price),
                        "stop_loss": float(stop_loss),
                        "pnl_pct": float(pnl_pct),
                        "direction": position.direction,
                        "atr": float(atr_current),
                        "price": context.current_price,
                    },
                ))

                # Clear position state
                del self._position_state[instrument]
                return signals  # Exit immediately, don't look for new entries

        # Check for entry signals (EMA crossover)
        bullish_cross = fast_prev <= slow_prev and fast_current > slow_current
        bearish_cross = fast_prev >= slow_prev and fast_current < slow_current

        if bullish_cross:
            # Enter long position
            stop_loss = self._calculate_stop_loss(current_price, atr_current, "long")

            # Create position state
            self._position_state[instrument] = PositionState(
                direction="long",
                entry_price=current_price,
                stop_loss=stop_loss,
                highest_price=current_price,
            )

            # Calculate signal strength
            cross_magnitude = (fast_current - slow_current) / slow_current
            strength = min(1.0, 0.5 + abs(cross_magnitude) * 50)

            signals.append(self.create_signal(
                signal_type=SignalType.BUY,
                instrument=instrument,
                strength=strength,
                reason=f"Bullish EMA crossover with ATR trailing stop at {stop_loss:.5f}",
                metadata={
                    "signal_category": "entry",
                    "direction": "long",
                    "entry_price": float(current_price),
                    "initial_stop": float(stop_loss),
                    "atr": float(atr_current),
                    "ema_fast": float(fast_current),
                    "ema_slow": float(slow_current),
                    "price": context.current_price,
                },
            ))

        elif bearish_cross:
            # Enter short position
            stop_loss = self._calculate_stop_loss(current_price, atr_current, "short")

            # Create position state
            self._position_state[instrument] = PositionState(
                direction="short",
                entry_price=current_price,
                stop_loss=stop_loss,
                lowest_price=current_price,
            )

            # Calculate signal strength
            cross_magnitude = (slow_current - fast_current) / slow_current
            strength = min(1.0, 0.5 + abs(cross_magnitude) * 50)

            signals.append(self.create_signal(
                signal_type=SignalType.SELL,
                instrument=instrument,
                strength=strength,
                reason=f"Bearish EMA crossover with ATR trailing stop at {stop_loss:.5f}",
                metadata={
                    "signal_category": "entry",
                    "direction": "short",
                    "entry_price": float(current_price),
                    "initial_stop": float(stop_loss),
                    "atr": float(atr_current),
                    "ema_fast": float(fast_current),
                    "ema_slow": float(slow_current),
                    "price": context.current_price,
                },
            ))

        return signals

    def on_stop(self) -> None:
        """Clear position state when strategy stops."""
        super().on_stop()
        self._position_state.clear()

    def get_position_state(self, instrument: str) -> PositionState | None:
        """Get current position state for an instrument."""
        return self._position_state.get(instrument)

    def clear_position(self, instrument: str) -> None:
        """Manually clear position state for an instrument."""
        if instrument in self._position_state:
            del self._position_state[instrument]

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        ema_fast = self.params.get("ema_fast", 10)
        ema_slow = self.params.get("ema_slow", 20)
        atr_period = self.params.get("atr_period", 14)
        atr_multiplier = self.params.get("atr_multiplier", 2.0)

        if ema_fast >= ema_slow:
            errors.append("Fast EMA must be less than slow EMA")

        if atr_period < 5:
            errors.append("ATR period must be at least 5")

        if atr_multiplier <= 0:
            errors.append("ATR multiplier must be positive")

        if atr_multiplier > 10:
            errors.append("ATR multiplier should not exceed 10")

        return errors
