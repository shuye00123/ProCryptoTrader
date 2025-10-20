# ProCryptoTrader

一个专业的加密货币量化交易系统，支持多交易所、多策略、多时间框架的自动化交易。

## 特性

- **多交易所支持**：支持Binance、OKX等主流交易所
- **多策略框架**：内置网格策略、马丁格尔策略，支持自定义策略
- **多时间框架**：支持1分钟、5分钟、1小时、1天等多种时间框架
- **回测系统**：提供完整的回测引擎和绩效评估指标
- **风险管理**：内置风险控制工具，支持仓位管理、止损止盈
- **数据分析**：提供交易结果分析、可视化绘图、因子效果评估
- **实盘交易**：多交易所支持、多策略并行执行、实时监控与通知

## 项目结构

```
ProCryptoTrader/
├── core/                    # 核心模块
│   ├── analysis/           # 分析模块
│   ├── backtest/           # 回测模块
│   ├── data/               # 数据模块
│   ├── exchange/           # 交易所接口
│   ├── live/               # 实盘交易模块
│   ├── strategy/           # 策略模块
│   └── utils/              # 工具模块
├── configs/                # 配置文件
├── docs/                   # 文档
├── examples/               # 示例代码
├── tests/                  # 单元测试
├── requirements.txt        # 依赖库
└── setup.py               # 安装脚本
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置交易所API

编辑 `configs/live_config.yaml` 文件，添加您的交易所API密钥：

```yaml
exchanges:
  binance:
    api_key: "your_api_key"
    secret: "your_secret"
    sandbox: true  # 测试环境
```

### 运行回测

```bash
python examples/backtest_example.py
```

### 运行实盘交易

```bash
python examples/live_example.py
```

## 策略示例

### 网格策略

网格策略是在价格区间内设置多个买入和卖出点位，通过价格波动赚取差价的策略。

```python
from core.strategy.grid_strategy import GridStrategy

# 创建网格策略
strategy = GridStrategy({
    "grid_size": 0.01,      # 网格大小 1%
    "grid_levels": 10,      # 网格层数
    "order_size": 0.01,     # 订单大小
    "take_profit": 0.02,    # 止盈 2%
    "stop_loss": 0.05       # 止损 5%
})
```

### 马丁格尔策略

马丁格尔策略是在亏损时加倍下注的策略，通过连续获胜覆盖之前的亏损。

```python
from core.strategy.martingale_strategy import MartingaleStrategy

# 创建马丁格尔策略
strategy = MartingaleStrategy({
    "base_order_size": 0.01,  # 基础订单大小
    "multiplier": 2.0,         # 加倍倍数
    "max_levels": 5,           # 最大层数
    "take_profit": 0.02,       # 止盈 2%
    "stop_loss": 0.1           # 止损 10%
})
```

## 自定义策略

您可以通过继承 `BaseStrategy` 类来创建自定义策略：

```python
from core.strategy.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        # 初始化策略参数
    
    def generate_signal(self, data):
        # 实现信号生成逻辑
        # 返回: {"type": "buy/sell/hold", "amount": 0.01, "price": 50000}
        pass
    
    def update(self, data):
        # 更新策略状态
        pass
```

## 回测系统

回测系统支持多策略、多时间框架、多交易对的回测，并提供详细的绩效评估指标。

```python
from core.backtest.backtester import Backtester
from core.data.data_loader import DataLoader

# 加载数据
data_loader = DataLoader()
data = data_loader.load_csv("BTC_USDT_1h.csv")

# 创建回测引擎
backtester = Backtester(
    initial_balance=10000,
    commission=0.001,
    slippage=0.0005
)

# 运行回测
results = backtester.run(strategy, data)

# 查看结果
print(f"总收益率: {results['metrics']['total_return']:.2%}")
print(f"夏普比率: {results['metrics']['sharpe_ratio']:.2f}")
print(f"最大回撤: {results['metrics']['max_drawdown']:.2%}")
```

## 风险管理

系统提供多种风险管理工具，帮助您控制交易风险：

```python
from core.utils.risk_tools import RiskManager

# 创建风险管理器
risk_manager = RiskManager()

# 设置最大仓位
risk_manager.max_position_size = 0.1  # 最大仓位10%

# 设置最大回撤
risk_manager.max_drawdown = 0.1  # 最大回撤10%

# 检查交易是否合规
is_valid = risk_manager.check_position_size("BTC/USDT", 0.01, 50000)
```

## 数据管理

系统支持从交易所获取历史数据，并进行本地存储和管理：

```python
from core.data.data_fetcher import DataFetcher
from core.data.data_manager import DataManager

# 获取数据
fetcher = DataFetcher()
data = fetcher.fetch_ohlcv("binance", "BTC/USDT", "1h", limit=1000)

# 存储数据
manager = DataManager()
manager.save_data(data, "BTC/USDT", "1h")

# 加载数据
data = manager.load_data("BTC/USDT", "1h")
```

## 文档

- [API文档](docs/api.md)
- [策略开发指南](docs/strategy_guide.md)
- [回测系统使用指南](docs/backtest_guide.md)
- [实盘交易使用指南](docs/live_trading_guide.md)

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 许可证

MIT License

## 联系方式

如有问题，请通过以下方式联系：

- 邮箱：your_email@example.com
- GitHub：https://github.com/your_username/ProCryptoTrader

## 免责声明

本软件仅供学习和研究使用，不构成投资建议。使用本软件进行实盘交易所造成的任何损失，开发者不承担责任。请在充分了解风险的情况下使用。