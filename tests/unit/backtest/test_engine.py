"""Tests for backtest engine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingsystem.backtest.engine import BacktestEngine, Position
from tradingsystem.models.backtest import BacktestConfig, BacktestTrade
from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext


# --- Fixtures ---


@pytest.fixture
def sample_config():
    """Create sample backtest configuration."""
    return BacktestConfig(
        strategy_id="test_strategy",
        instrument="EUR_USD",
        period="1h",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
        initial_capital=Decimal("10000"),
        position_size_pct=Decimal("10"),
        commission_pct=Decimal("0.001"),
        slippage_pct=Decimal("0.0001"),
    )


@pytest.fixture
def sample_candles():
    """Create sample OHLCV data."""
    dates = pd.date_range(
        start="2024-01-01",
        periods=100,
        freq="1h",
        tz=timezone.utc,
    )
    data = {
        "open": [1.0850 + i * 0.0001 for i in range(100)],
        "high": [1.0860 + i * 0.0001 for i in range(100)],
        "low": [1.0840 + i * 0.0001 for i in range(100)],
        "close": [1.0855 + i * 0.0001 for i in range(100)],
        "volume": [1000 + i * 10 for i in range(100)],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def trending_candles():
    """Create trending OHLCV data for crossover tests."""
    dates = pd.date_range(
        start="2024-01-01",
        periods=50,
        freq="1h",
        tz=timezone.utc,
    )
    # First half: downtrend, second half: uptrend
    prices = []
    for i in range(50):
        if i < 25:
            prices.append(1.10 - i * 0.002)  # Downtrend
        else:
            prices.append(1.05 + (i - 25) * 0.002)  # Uptrend

    data = {
        "open": prices,
        "high": [p + 0.001 for p in prices],
        "low": [p - 0.001 for p in prices],
        "close": prices,
        "volume": [1000] * 50,
    }
    return pd.DataFrame(data, index=dates)


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""

    name = "Mock Strategy"
    description = "Test strategy"
    instruments = ["EUR_USD"]
    periods = ["1h"]
    required_indicators = []

    def __init__(self, signals_to_generate=None, **params):
        super().__init__(**params)
        self.signals_to_generate = signals_to_generate or []
        self.call_count = 0

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        self.call_count += 1
        if self.call_count - 1 < len(self.signals_to_generate):
            signal_config = self.signals_to_generate[self.call_count - 1]
            if signal_config:
                return [self.create_signal(
                    signal_type=signal_config["type"],
                    instrument=context.instrument,
                    strength=signal_config.get("strength", 0.8),
                    reason=signal_config.get("reason", "Test signal"),
                )]
        return []


# --- Position Tests ---


class TestPosition:
    """Tests for Position class."""

    def test_position_init_long(self):
        """Should initialize LONG position correctly."""
        pos = Position(
            side="LONG",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
            signal_reason="Test buy",
        )

        assert pos.side == "LONG"
        assert pos.entry_price == Decimal("1.0850")
        assert pos.quantity == Decimal("1000")
        assert pos.signal_reason == "Test buy"

    def test_position_init_short(self):
        """Should initialize SHORT position correctly."""
        pos = Position(
            side="SHORT",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
        )

        assert pos.side == "SHORT"

    def test_calculate_pnl_long_profit(self):
        """Should calculate profit for LONG position."""
        pos = Position(
            side="LONG",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
        )

        pnl = pos.calculate_pnl(Decimal("1.0900"))

        # (1.0900 - 1.0850) * 1000 = 5.00
        assert pnl == Decimal("5.00")

    def test_calculate_pnl_long_loss(self):
        """Should calculate loss for LONG position."""
        pos = Position(
            side="LONG",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
        )

        pnl = pos.calculate_pnl(Decimal("1.0800"))

        # (1.0800 - 1.0850) * 1000 = -5.00
        assert pnl == Decimal("-5.00")

    def test_calculate_pnl_short_profit(self):
        """Should calculate profit for SHORT position."""
        pos = Position(
            side="SHORT",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
        )

        pnl = pos.calculate_pnl(Decimal("1.0800"))

        # (1.0850 - 1.0800) * 1000 = 5.00
        assert pnl == Decimal("5.00")

    def test_calculate_pnl_short_loss(self):
        """Should calculate loss for SHORT position."""
        pos = Position(
            side="SHORT",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=datetime.now(timezone.utc),
        )

        pnl = pos.calculate_pnl(Decimal("1.0900"))

        # (1.0850 - 1.0900) * 1000 = -5.00
        assert pnl == Decimal("-5.00")

    def test_close_position(self):
        """Should create BacktestTrade when closing position."""
        entry_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)

        pos = Position(
            side="LONG",
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            entry_time=entry_time,
            signal_reason="Buy signal",
        )

        trade = pos.close(
            exit_price=Decimal("1.0900"),
            exit_time=exit_time,
            commission=Decimal("1.00"),
        )

        assert isinstance(trade, BacktestTrade)
        assert trade.entry_time == entry_time
        assert trade.exit_time == exit_time
        assert trade.side == "LONG"
        assert trade.entry_price == Decimal("1.0850")
        assert trade.exit_price == Decimal("1.0900")
        assert trade.commission == Decimal("1.00")
        # PnL = (1.0900 - 1.0850) * 1000 - 1.00 = 4.00
        assert trade.pnl == Decimal("4.00")


# --- BacktestEngine Tests ---


class TestBacktestEngineInit:
    """Tests for BacktestEngine initialization."""

    def test_init_with_config(self, sample_config):
        """Should initialize with configuration."""
        engine = BacktestEngine(sample_config)

        assert engine.config == sample_config
        assert engine.capital == sample_config.initial_capital
        assert engine.position is None
        assert engine.trades == []
        assert engine.equity_curve == []
        assert engine.peak_equity == sample_config.initial_capital


class TestBacktestEngineRun:
    """Tests for BacktestEngine.run()."""

    def test_run_empty_candles_raises(self, sample_config):
        """Should raise ValueError for empty candles."""
        engine = BacktestEngine(sample_config)
        strategy = MockStrategy()
        empty_df = pd.DataFrame()

        with pytest.raises(ValueError, match="No candle data"):
            engine.run(strategy, empty_df)

    def test_run_no_signals(self, sample_config, sample_candles):
        """Should complete run with no signals."""
        engine = BacktestEngine(sample_config)
        strategy = MockStrategy(signals_to_generate=[])

        result = engine.run(strategy, sample_candles)

        assert result.strategy_id == "test_strategy"
        assert result.instrument == "EUR_USD"
        assert result.initial_capital == Decimal("10000")
        assert result.final_capital == Decimal("10000")  # No trades
        assert len(result.trades) == 0
        assert len(result.equity_curve) == len(sample_candles)

    def test_run_with_buy_signal(self, sample_config, sample_candles):
        """Should open position on BUY signal."""
        engine = BacktestEngine(sample_config)
        # Generate BUY signal on first candle
        signals = [{"type": SignalType.BUY}] + [None] * 99
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        # Position should be closed at end
        assert len(result.trades) == 1
        assert result.trades[0].side == "LONG"

    def test_run_with_sell_signal(self, sample_config, sample_candles):
        """Should open SHORT position on SELL signal."""
        engine = BacktestEngine(sample_config)
        signals = [{"type": SignalType.SELL}] + [None] * 99
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        assert len(result.trades) == 1
        assert result.trades[0].side == "SHORT"

    def test_run_hold_signal_no_action(self, sample_config, sample_candles):
        """Should take no action on HOLD signal."""
        engine = BacktestEngine(sample_config)
        signals = [{"type": SignalType.HOLD}] * 100
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        assert len(result.trades) == 0

    def test_run_buy_then_sell_closes_position(self, sample_config, sample_candles):
        """Should close LONG and open SHORT on opposite signal."""
        engine = BacktestEngine(sample_config)
        signals = [{"type": SignalType.BUY}] + [None] * 48 + [{"type": SignalType.SELL}] + [None] * 50
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        # First trade: LONG closed by SELL, second trade: SHORT closed at end
        assert len(result.trades) == 2
        assert result.trades[0].side == "LONG"
        assert result.trades[1].side == "SHORT"

    def test_run_equity_curve_tracks_value(self, sample_config, sample_candles):
        """Should track equity curve throughout backtest."""
        engine = BacktestEngine(sample_config)
        strategy = MockStrategy(signals_to_generate=[])

        result = engine.run(strategy, sample_candles)

        assert len(result.equity_curve) == len(sample_candles)
        for point in result.equity_curve:
            assert point.equity == Decimal("10000")  # No positions = no change
            assert point.drawdown == Decimal("0")

    def test_run_calculates_metrics(self, sample_config, sample_candles):
        """Should calculate performance metrics."""
        engine = BacktestEngine(sample_config)
        signals = [{"type": SignalType.BUY}] + [None] * 99
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        assert result.metrics is not None
        assert result.metrics.total_trades == 1
        assert result.metrics.win_rate is not None


class TestBacktestEngineIndicators:
    """Tests for indicator calculation."""

    def test_calculate_indicators_with_pandas_ta(self, sample_config, sample_candles):
        """Should calculate pandas_ta indicators."""
        engine = BacktestEngine(sample_config)

        class StrategyWithIndicators(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["1h"]

            @property
            def required_indicators(self):
                return [
                    IndicatorConfig("sma", {"length": 10}, "sma_10"),
                ]

            def generate_signals(self, context):
                return []

        strategy = StrategyWithIndicators()

        with patch("tradingsystem.backtest.engine.calculate_pandas_ta_indicator") as mock_calc:
            mock_calc.return_value = pd.Series([1.0] * len(sample_candles))

            result = engine.run(strategy, sample_candles)

            mock_calc.assert_called()

    def test_calculate_indicators_with_custom(self, sample_config, sample_candles):
        """Should calculate custom indicators from registry."""
        engine = BacktestEngine(sample_config)

        class StrategyWithCustomIndicator(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["1h"]

            @property
            def required_indicators(self):
                return [
                    IndicatorConfig("custom_indicator", {}, "custom"),
                ]

            def generate_signals(self, context):
                return []

        strategy = StrategyWithCustomIndicator()

        mock_indicator_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.calculate.return_value = pd.Series([1.0] * len(sample_candles))
        mock_indicator_class.return_value = mock_instance

        with patch("tradingsystem.backtest.engine.IndicatorRegistry.get") as mock_get:
            mock_get.return_value = mock_indicator_class

            result = engine.run(strategy, sample_candles)

            mock_get.assert_called_with("custom_indicator")


class TestBacktestEngineSlippage:
    """Tests for slippage handling."""

    def test_slippage_applied_on_buy(self, sample_config, sample_candles):
        """Should add slippage to buy price."""
        engine = BacktestEngine(sample_config)
        signals = [{"type": SignalType.BUY}] + [None] * 99
        strategy = MockStrategy(signals_to_generate=signals)

        result = engine.run(strategy, sample_candles)

        # Entry price should be higher than close due to slippage
        first_close = Decimal(str(sample_candles.iloc[0]["close"]))
        expected_slippage = first_close * sample_config.slippage_pct
        expected_entry = first_close + expected_slippage

        assert result.trades[0].entry_price == expected_entry


class TestBacktestEngineDrawdown:
    """Tests for drawdown calculation."""

    def test_drawdown_tracks_peak(self, sample_config, sample_candles):
        """Should track peak equity and calculate drawdown."""
        engine = BacktestEngine(sample_config)

        # Manually set up for drawdown test
        engine.peak_equity = Decimal("11000")

        equity = Decimal("10500")
        drawdown, drawdown_pct = engine._calculate_drawdown(equity)

        assert drawdown == Decimal("500")
        assert drawdown_pct == Decimal("500") / Decimal("11000") * 100

    def test_drawdown_updates_peak(self, sample_config):
        """Should update peak when equity increases."""
        engine = BacktestEngine(sample_config)

        equity = Decimal("11000")
        engine._calculate_drawdown(equity)

        assert engine.peak_equity == Decimal("11000")


class TestBacktestEngineMetrics:
    """Tests for metrics calculation."""

    def test_metrics_with_winning_trades(self, sample_config):
        """Should calculate win rate for winning trades."""
        engine = BacktestEngine(sample_config)
        engine.trades = [
            BacktestTrade(
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("50"),
                pnl_pct=Decimal("0.46"),
                commission=Decimal("1"),
            )
        ]
        engine.equity_curve = []

        metrics = engine._calculate_metrics()

        assert metrics.total_trades == 1
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 0
        assert metrics.win_rate == 100.0

    def test_metrics_with_losing_trades(self, sample_config):
        """Should calculate win rate for losing trades."""
        engine = BacktestEngine(sample_config)
        engine.trades = [
            BacktestTrade(
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0800"),
                quantity=Decimal("1000"),
                pnl=Decimal("-50"),
                pnl_pct=Decimal("-0.46"),
                commission=Decimal("1"),
            )
        ]
        engine.equity_curve = []

        metrics = engine._calculate_metrics()

        assert metrics.total_trades == 1
        assert metrics.winning_trades == 0
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 0.0

    def test_metrics_profit_factor(self, sample_config):
        """Should calculate profit factor."""
        engine = BacktestEngine(sample_config)
        engine.trades = [
            BacktestTrade(
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("100"),
                pnl_pct=Decimal("1"),
                commission=Decimal("0"),
            ),
            BacktestTrade(
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0800"),
                quantity=Decimal("1000"),
                pnl=Decimal("-50"),
                pnl_pct=Decimal("-0.5"),
                commission=Decimal("0"),
            ),
        ]
        engine.equity_curve = []

        metrics = engine._calculate_metrics()

        # Profit factor = 100 / 50 = 2.0
        assert metrics.profit_factor == 2.0

    def test_metrics_avg_trade_duration(self, sample_config):
        """Should calculate average trade duration."""
        engine = BacktestEngine(sample_config)
        entry = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        exit1 = datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)  # 2 hours = 120 min
        exit2 = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)  # 1 hour = 60 min

        engine.trades = [
            BacktestTrade(
                entry_time=entry,
                exit_time=exit1,
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("50"),
                pnl_pct=Decimal("0.5"),
                commission=Decimal("0"),
            ),
            BacktestTrade(
                entry_time=entry,
                exit_time=exit2,
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("50"),
                pnl_pct=Decimal("0.5"),
                commission=Decimal("0"),
            ),
        ]
        engine.equity_curve = []

        metrics = engine._calculate_metrics()

        # Average = (120 + 60) / 2 = 90 minutes
        assert metrics.avg_trade_duration == 90.0
