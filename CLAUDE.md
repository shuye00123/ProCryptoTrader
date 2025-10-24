# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProCryptoTrader is a professional cryptocurrency quantitative trading system supporting multi-exchange, multi-strategy, and multi-timeframe automated trading. The system follows the **RIPER-5 principles**: Risk first, Integration minimal, Predictability, Expandability, and Realistic evaluation.

## Common Development Commands

### Running Tests
```bash
# Run all tests
python tests/run_tests.py

# Run specific test module
python tests/run_tests.py test_backtest
python tests/run_tests.py test_data
python tests/run_tests.py test_strategies
python tests/run_tests.py test_trading
python tests/run_tests.py test_utils
```

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install project in development mode
pip install -e .
```

### Running Examples
```bash
# Run backtest examples
python examples/backtest_example.py

# Run live trading example
python examples/live_example.py

# Run strategy example
python examples/strategy_example.py
```

### Configuration Management
Configuration files are stored in YAML format in the `configs/` directory:
- `backtest_config.yaml` - Backtesting configuration
- `live_config.yaml` - Live trading configuration
- `logging_config.yaml` - Logging configuration

## Architecture Overview

### Core Directory Structure
```
core/
├── analysis/       # Performance analysis and visualization
├── backtest/       # Backtesting engine and metrics
├── data/          # Data fetching, management, and processing
├── exchange/      # Exchange API adapters (Binance, OKX, etc.)
├── live/          # Live trading execution
├── strategy/      # Trading strategies and base classes
├── trading/       # Order management and position tracking
└── utils/         # Utilities (logging, config, risk management)
```

### Key Components

#### Data Module (`core/data/`)
- **data_fetcher.py**: Fetches OHLCV data using ccxt library
- **data_manager.py**: Manages local data storage and caching
- **data_loader.py**: Loads historical data from files (CSV, JSON, Parquet)
- **data_processor.py**: Processes and transforms raw data
- **data_storage.py**: Handles data persistence

#### Strategy Module (`core/strategy/`)
- **base_strategy.py**: Abstract base class for all strategies
- **grid_strategy.py**: Grid trading strategy implementation
- **martingale_strategy.py**: Martingale strategy implementation
- **dual_ma_strategy.py**: Dual moving average strategy

#### Backtest Module (`core/backtest/`)
- **backtester.py**: Main backtesting engine
- **metrics.py**: Performance metrics calculation
- **report_generator.py**: HTML/PDF/Markdown report generation

#### Live Trading Module (`core/live/`)
- **live_trader.py**: Main live trading controller
- **config_loader.py**: Live trading configuration management

#### Exchange Module (`core/exchange/`)
- **base_exchange.py**: Abstract interface for exchange implementations
- **binance_api.py**: Binance API implementation
- **okx_api.py**: OKX API implementation

#### Trading Module (`core/trading/`)
- **order_manager.py**: Order placement and management
- **position_manager.py**: Position tracking and management

#### Risk Management (`core/utils/`)
- **risk_manager.py**: Risk controls and position sizing
- **risk_control.py**: Risk validation and monitoring
- **risk_tools.py**: Risk calculation utilities

### Strategy Development

#### Creating Custom Strategies
All strategies must inherit from `BaseStrategy` and implement:
- `__init__(self, config)`: Initialize strategy parameters
- `generate_signal(self, data)`: Generate trading signals
- `update(self, data)`: Update strategy state

#### Signal Format
Trading signals should return a dictionary with:
```python
{
    "type": "buy/sell/hold",
    "amount": 0.01,
    "price": 50000,
    "stop_loss": 48000,
    "take_profit": 52000
}
```

### Data Flow

1. **Data Collection**: `data_fetcher.py` → `data_manager.py` → local storage
2. **Strategy Execution**: `data_loader.py` → `strategy.py` → trading signals
3. **Backtesting**: `backtester.py` simulates strategy execution on historical data
4. **Live Trading**: `live_trader.py` executes signals via exchange APIs

### Configuration System

The system uses YAML configuration files with environment variable support:
```yaml
# Example configuration
exchange:
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  sandbox: true
```

### Testing Strategy

- Unit tests for each module in `tests/` directory
- Integration tests for data flow and strategy execution
- Mock data for reproducible testing
- Test data generation in example scripts

### Risk Management Integration

Risk management is integrated at multiple levels:
- Pre-trade validation in `risk_manager.py`
- Position sizing limits in `position_manager.py`
- Global risk limits enforced in `live_trader.py`
- Emergency stop mechanisms

### Exchange Integration

New exchanges can be added by:
1. Inheriting from `base_exchange.py`
2. Implementing required methods: `place_order()`, `cancel_order()`, `get_balance()`, etc.
3. Adding exchange-specific configuration

### Performance Optimization

- Use Parquet format for efficient data storage
- Implement vectorized operations in pandas
- Cache frequently accessed data
- Batch API requests where possible
- Async I/O for data fetching (planned)

### Monitoring and Logging

- Structured logging via `utils/logger.py`
- Trade execution logs for audit trails
- Performance metrics tracking
- Alert system integration (Telegram/email planned)

## Development Notes

- Use pandas DataFrames for all time-series data
- Follow PEP 8 style guidelines
- All timestamps should be timezone-aware (UTC)
- Error handling should be comprehensive but non-blocking
- API rate limits must be respected for all exchange integrations
- Use environment variables for sensitive configuration (API keys, secrets)

## Data Formats

### OHLCV Data Structure
```python
pd.DataFrame({
    'timestamp': pd.DatetimeIndex,
    'open': float64,
    'high': float64,
    'low': float64,
    'close': float64,
    'volume': float64
})
```

### Configuration Schema
All configuration files should validate against their respective schemas defined in the codebase.

## Important Design Patterns

- **Strategy Pattern**: Different trading strategies implement common interface
- **Adapter Pattern**: Exchange APIs adapt to common interface
- **Observer Pattern**: Risk management observes trading activities
- **Factory Pattern**: Strategy and exchange instances created from configuration