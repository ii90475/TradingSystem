"""Service for generating strategy code from plain English using Claude."""

import ast
import logging
import re
from pathlib import Path

import anthropic

from tradingsystem.core.config import settings
from tradingsystem.strategies.base import BaseStrategy
from tradingsystem.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

# Directory for user-generated strategies
USER_STRATEGIES_DIR = Path(__file__).parent.parent / "strategies" / "generated"

SYSTEM_PROMPT = """\
You are a trading strategy code generator. You generate Python code that implements \
a trading strategy as a BaseStrategy subclass for the TradingSystem platform.

## Framework

Every strategy must:
1. Import from the framework:
   ```python
   import pandas as pd
   from tradingsystem.models.signal import Signal, SignalType
   from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
   from tradingsystem.strategies.registry import StrategyRegistry
   ```

2. Use the `@StrategyRegistry.register("strategy_id")` decorator with a unique snake_case ID.

3. Subclass `BaseStrategy` and set class attributes:
   - `name`: Human-readable name
   - `description`: What the strategy does
   - `version`: Semantic version (start at "1.0.0")
   - `author`: Set to "Generated"
   - `instruments`: List of currency pairs (e.g., ["EUR_USD", "GBP_USD"])
   - `periods`: List of timeframes (e.g., ["M5", "H1", "D"])
   - `default_params`: Dict of configurable parameters with defaults

4. Define `required_indicators` as a property returning `list[IndicatorConfig]`. \
Each IndicatorConfig has: indicator_type (str), params (dict), column_name (optional str).
   Available indicator types: sma, ema, rsi, bbands, macd, atr, stoch, adx, cci, willr, \
obv, vwap, ichimoku, supertrend, psar.

5. Implement `generate_signals(self, context: StrategyContext) -> list[Signal]`:
   - Access candles via `context.candles` (DataFrame with columns: time, open, high, low, close, volume)
   - Access indicators via `context.indicators` (dict mapping column_name to pd.Series)
   - Check for None/NaN values before using indicators
   - Need at least 2 data points for crossover detection
   - Return a list of Signal objects created with `self.create_signal()`
   - `self.create_signal(signal_type, instrument, strength, reason, metadata)`
   - `signal_type` is `SignalType.BUY`, `SignalType.SELL`, or `SignalType.HOLD`
   - `strength` is a float from 0.0 to 1.0
   - `reason` is a human-readable explanation
   - `metadata` is an optional dict with numeric values for debugging

## Example

```python
import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("ma_crossover")
class MACrossoverStrategy(BaseStrategy):
    name = "MA Crossover"
    description = "Trend-following strategy using moving average crossovers"
    version = "1.0.0"
    author = "TradingSystem"
    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M1", "M5", "15m", "1h"]
    default_params = {
        "fast_period": 10,
        "slow_period": 20,
        "ma_type": "ema",
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        ma_type = self.params.get("ma_type", "ema")
        fast_period = self.params.get("fast_period", 10)
        slow_period = self.params.get("slow_period", 20)
        return [
            IndicatorConfig(indicator_type=ma_type, params={"length": fast_period}, column_name="fast_ma"),
            IndicatorConfig(indicator_type=ma_type, params={"length": slow_period}, column_name="slow_ma"),
        ]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        signals = []
        fast_ma = context.indicators.get("fast_ma")
        slow_ma = context.indicators.get("slow_ma")
        if fast_ma is None or slow_ma is None:
            return signals
        if len(fast_ma) < 2 or len(slow_ma) < 2:
            return signals

        fast_current = fast_ma.iloc[-1]
        fast_prev = fast_ma.iloc[-2]
        slow_current = slow_ma.iloc[-1]
        slow_prev = slow_ma.iloc[-2]

        if pd.isna(fast_current) or pd.isna(fast_prev) or pd.isna(slow_current) or pd.isna(slow_prev):
            return signals

        if fast_prev <= slow_prev and fast_current > slow_current:
            diff = (fast_current - slow_current) / slow_current
            strength = min(1.0, abs(diff) * 100)
            signals.append(self.create_signal(
                signal_type=SignalType.BUY,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bullish crossover: fast MA crossed above slow MA",
                metadata={"fast_ma": float(fast_current), "slow_ma": float(slow_current), "price": context.current_price},
            ))
        elif fast_prev >= slow_prev and fast_current < slow_current:
            diff = (slow_current - fast_current) / slow_current
            strength = min(1.0, abs(diff) * 100)
            signals.append(self.create_signal(
                signal_type=SignalType.SELL,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bearish crossover: fast MA crossed below slow MA",
                metadata={"fast_ma": float(fast_current), "slow_ma": float(slow_current), "price": context.current_price},
            ))
        return signals
```

## Rules
- Output ONLY the Python code. No explanations, no markdown fences, no commentary.
- Use only the imports listed above. Do not import anything else.
- Always check for None and NaN before using indicator values.
- Always use `self.params.get()` with defaults for parameter access.
- The strategy_id in the register decorator must be unique snake_case.
- Set `author = "Generated"` to distinguish from hand-written strategies.
"""


def _get_client() -> anthropic.Anthropic:
    """Get an Anthropic client."""
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _extract_strategy_id(code: str) -> str | None:
    """Extract the strategy_id from the @StrategyRegistry.register() decorator."""
    match = re.search(r'@StrategyRegistry\.register\(["\'](\w+)["\']\)', code)
    return match.group(1) if match else None


def _extract_class_name(code: str) -> str | None:
    """Extract the class name from the strategy code."""
    match = re.search(r'class\s+(\w+)\s*\(BaseStrategy\)', code)
    return match.group(1) if match else None


def validate_strategy_code(code: str) -> list[str]:
    """
    Validate that strategy code follows the BaseStrategy pattern.

    Returns list of error messages (empty if valid).
    """
    errors = []

    # Check syntax
    try:
        ast.parse(code)
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return errors

    # Check required imports
    if "from tradingsystem.strategies.base import BaseStrategy" not in code:
        errors.append("Missing BaseStrategy import")

    if "from tradingsystem.strategies.registry import StrategyRegistry" not in code:
        errors.append("Missing StrategyRegistry import")

    if "from tradingsystem.models.signal import" not in code:
        errors.append("Missing Signal/SignalType import")

    # Check decorator
    strategy_id = _extract_strategy_id(code)
    if not strategy_id:
        errors.append("Missing @StrategyRegistry.register() decorator")

    # Check class definition
    class_name = _extract_class_name(code)
    if not class_name:
        errors.append("No class inheriting from BaseStrategy found")

    # Check generate_signals method
    if "def generate_signals" not in code:
        errors.append("Missing generate_signals method")

    # Check required_indicators
    if "required_indicators" not in code:
        errors.append("Missing required_indicators property")

    # Security: check for dangerous imports/calls
    dangerous_patterns = [
        r'\bimport\s+os\b',
        r'\bimport\s+subprocess\b',
        r'\bimport\s+sys\b',
        r'\bimport\s+shutil\b',
        r'\b__import__\b',
        r'\beval\b\s*\(',
        r'\bexec\b\s*\(',
        r'\bopen\b\s*\(',
        r'\bcompile\b\s*\(',
        r'\bglobals\b\s*\(',
        r'\bgetattr\b\s*\(',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            errors.append(f"Disallowed pattern found: {pattern}")

    # Check only allowed imports
    import_lines = re.findall(r'^(?:from|import)\s+.+$', code, re.MULTILINE)
    allowed_prefixes = [
        "import pandas",
        "from tradingsystem.models.signal import",
        "from tradingsystem.strategies.base import",
        "from tradingsystem.strategies.registry import",
    ]
    for line in import_lines:
        line = line.strip()
        if not any(line.startswith(p) for p in allowed_prefixes):
            errors.append(f"Disallowed import: {line}")

    return errors


async def generate_strategy(description: str) -> dict:
    """
    Generate strategy code from a plain English description.

    Args:
        description: Plain English description of entry/exit conditions.

    Returns:
        Dict with 'code', 'strategy_id', 'class_name', and 'validation_errors'.
    """
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": description},
        ],
    )

    code = message.content[0].text.strip()

    # Strip markdown fences if Claude included them despite instructions
    if code.startswith("```"):
        lines = code.split("\n")
        # Remove first line (```python) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        code = "\n".join(lines)

    strategy_id = _extract_strategy_id(code)
    class_name = _extract_class_name(code)
    validation_errors = validate_strategy_code(code)

    return {
        "code": code,
        "strategy_id": strategy_id,
        "class_name": class_name,
        "validation_errors": validation_errors,
    }


def save_strategy(code: str) -> dict:
    """
    Save validated strategy code to the generated strategies directory.

    Args:
        code: Python source code for the strategy.

    Returns:
        Dict with 'strategy_id', 'file_path', and 'registered'.

    Raises:
        ValueError: If code fails validation or strategy_id already exists.
    """
    errors = validate_strategy_code(code)
    if errors:
        raise ValueError(f"Validation failed: {'; '.join(errors)}")

    strategy_id = _extract_strategy_id(code)

    # Check for ID collision with existing strategies
    if StrategyRegistry.is_registered(strategy_id):
        raise ValueError(f"Strategy '{strategy_id}' already exists in registry")

    # Ensure generated directory exists
    USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)

    # Write strategy file
    file_path = USER_STRATEGIES_DIR / f"{strategy_id}.py"
    if file_path.exists():
        raise ValueError(f"Strategy file already exists: {file_path.name}")

    file_path.write_text(code)
    logger.info(f"Saved strategy to {file_path}")

    # Register the strategy by loading the file
    count = StrategyRegistry.discover_strategies(USER_STRATEGIES_DIR)
    registered = StrategyRegistry.is_registered(strategy_id)

    if not registered:
        # Clean up if registration failed
        file_path.unlink(missing_ok=True)
        raise ValueError("Strategy file saved but failed to register — check code validity")

    return {
        "strategy_id": strategy_id,
        "file_path": str(file_path),
        "registered": registered,
    }
