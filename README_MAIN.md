# ProCryptoTrader - 加密货币量化交易框架

## 项目概述

ProCryptoTrader是一个功能完整的加密货币量化交易框架，遵循**RIPER-5原则**：
- **Risk first**（风险优先）
- **Integration minimal**（最小侵入）
- **Predictability**（可预期性）
- **Expandability**（可扩展性）
- **Realistic evaluation**（真实可评估）

## 主要功能

### 🔄 数据管理
- 支持多交易所数据下载（币安、OKX等）
- 多时间框架数据存储（1m、5m、1h、4h、1d等）
- 高效的Parquet格式存储
- 自动数据验证和完整性检查

### 📊 策略系统
- **网格策略（Grid Strategy）**: 在价格区间内低买高卖
- **马丁格尔策略（Martingale Strategy）**: 亏损时加倍下注
- 可扩展的策略基类，支持自定义策略
- 完整的信号生成和管理系统

### 📈 回测系统
- 高性能历史数据回测
- 详细的绩效指标计算
- 可视化图表生成
- 完整的交易日志记录

### 🚀 实盘交易
- 支持模拟和实盘交易模式
- 多交易所API集成
- 实时风险控制
- 完整的订单管理系统

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository_url>
cd ProCryptoTrader

# 安装依赖
pip install -r requirements.txt
```

### 2. 主程序使用

项目提供了统一的命令行入口 `main.py`，支持以下功能：

#### 查看帮助
```bash
python main.py --help
```

#### 下载历史数据
```bash
# 下载币安BTC/USDT数据
python main.py download binance --symbols BTC/USDT --timeframes 1h 4h --start-date 2024-01-01 --end-date 2024-01-31

# 下载多个交易对
python main.py download binance --symbols BTC/USDT ETH/USDT --timeframes 1h
```

#### 查看可用策略
```bash
python main.py list-strategies
```

#### 检查本地数据
```bash
python main.py check-data
```

#### 验证配置文件
```bash
python main.py validate-config --config backtest_config.yaml
```

#### 运行回测
```bash
# 使用默认配置
python main.py backtest --config backtest_config.yaml

# 指定策略
python main.py backtest --config backtest_config.yaml --strategy Martingale
```

#### 运行实盘交易
```bash
# 模拟交易
python main.py live --config live_config.yaml

# 实盘交易（需要配置API密钥）
python main.py live --config live_config.yaml
```

## 配置文件

### 回测配置 (configs/backtest_config.yaml)
```yaml
basic:
  start_date: "2023-01-01"
  end_date: "2023-12-31"
  initial_balance: 10000

data:
  exchange: "binance"
  symbols: ["BTC/USDT", "ETH/USDT"]
  timeframes: ["1h", "4h"]

strategy:
  name: "GridStrategy"
  params:
    grid_count: 10
    grid_range_pct: 0.02

trading:
  commission: 0.001
  slippage: 0.0005
  position_size: 0.1
```

### 实盘配置 (configs/live_config.yaml)
```yaml
basic:
  mode: "paper"  # "paper" 或 "live"
  symbols: ["BTC/USDT"]

exchanges:
  binance:
    api_key: "your_api_key"
    secret: "your_secret"
    sandbox: true

strategies:
  - name: "Martingale"
    symbols: ["BTC/USDT"]
    timeframe: "1m"
    enabled: true
```

## 项目结构

```
ProCryptoTrader/
├── core/                       # 核心模块
│   ├── data/                   # 数据管理
│   │   ├── data_downloader.py  # 数据下载器
│   │   ├── data_loader.py      # 数据加载器
│   │   └── data_manager.py     # 数据管理器
│   ├── strategy/               # 策略模块
│   │   ├── base_strategy.py    # 策略基类
│   │   ├── grid_strategy.py    # 网格策略
│   │   └── martingale_strategy.py  # 马丁格尔策略
│   ├── backtest/              # 回测模块
│   │   ├── backtester.py      # 回测引擎
│   │   ├── metrics.py         # 绩效指标
│   │   └── report_generator.py # 报告生成
│   ├── live/                  # 实盘交易
│   │   ├── live_trader.py     # 实盘交易器
│   │   └── config_loader.py   # 配置加载器
│   ├── exchange/              # 交易所接口
│   │   ├── base_exchange.py   # 交易所基类
│   │   ├── binance_api.py     # 币安API
│   │   └── okx_api.py         # OKX API
│   └── utils/                 # 工具模块
│       ├── logger.py          # 日志系统
│       ├── config.py          # 配置管理
│       └── risk_control.py    # 风险控制
├── configs/                   # 配置文件
├── scripts/                   # 脚本工具
├── data/                      # 数据存储
├── results/                   # 回测结果
├── logs/                      # 日志文件
├── tests/                     # 单元测试
├── examples/                  # 示例代码
├── main.py                    # 主入口程序
└── README.md                  # 项目说明
```

## 策略说明

### 网格策略 (Grid Strategy)
- **原理**: 在设定价格区间内设置买卖网格，低买高卖获取收益
- **适用场景**: 震荡行情
- **参数**:
  - `grid_count`: 网格数量
  - `grid_range_pct`: 网格范围百分比
  - `position_size`: 仓位大小

### 马丁格尔策略 (Martingale Strategy)
- **原理**: 亏损时按倍数增加仓位，直到盈利为止
- **适用场景**: 高胜率策略
- **参数**:
  - `multiplier`: 加仓倍数
  - `max_levels`: 最大加仓级别
  - `base_position_size`: 基础仓位
  - `profit_target_pct`: 盈利目标

## 风险控制

### 内置风控机制
- 最大回撤限制
- 单笔最大亏损
- 日亏损限制
- 最大持仓数量
- 强制止损

### 使用建议
1. **充分回测**: 在实盘前进行充分的历史数据回测
2. **模拟交易**: 先进行模拟交易验证策略
3. **小额测试**: 实盘初期使用小额资金测试
4. **监控告警**: 设置合适的监控和告警机制
5. **定期回顾**: 定期回顾和调整策略参数

## 数据格式

### 存储格式
- 使用Parquet格式存储，支持高效压缩和查询
- 按交易所/交易对/时间框架组织目录结构
- 数据格式：OHLCV（开盘价、最高价、最低价、收盘价、成交量）

### 目录结构
```
data/
├── binance/
│   ├── BTC-USDT/
│   │   ├── 1h.parquet
│   │   ├── 4h.parquet
│   │   └── 1d.parquet
│   └── ETH-USDT/
│       ├── 1h.parquet
│       └── 4h.parquet
└── okx/
    └── ...
```

## 性能优化

### 回测性能
- 使用向量化计算加速
- 支持并行回测
- 内存优化的大数据处理
- 可配置的随机种子确保结果可复现

### 数据处理
- 高效的数据加载和缓存
- 支持数据增量更新
- 自动数据验证和修复

## 扩展开发

### 添加新策略
1. 继承`BaseStrategy`类
2. 实现`generate_signals`方法
3. 实现相应的技术指标计算
4. 在配置文件中添加策略参数

### 添加新交易所
1. 继承`BaseExchange`类
2. 实现交易所特定的API接口
3. 在数据下载器中添加支持
4. 更新配置文件模板

## 常见问题

### Q: 如何获取API密钥？
A: 访问对应交易所官网，注册账户后在API管理页面创建API密钥。建议先使用测试环境。

### Q: 回测结果不理想怎么办？
A:
1. 调整策略参数
2. 扩大回测时间范围
3. 尝试不同的市场环境
4. 考虑策略组合

### Q: 实盘交易风险如何控制？
A:
1. 设置合理的资金使用比例
2. 使用止损和止盈
3. 监控账户余额和持仓
4. 及时处理异常情况

## 贡献指南

欢迎提交Issue和Pull Request来改进项目！

### 开发规范
1. 遵循PEP 8代码规范
2. 添加必要的注释和文档
3. 编写单元测试
4. 确保向后兼容性

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 联系方式

如有问题或建议，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至项目维护者

---

**免责声明**: 本项目仅用于研究和教育目的。使用本程序进行实盘交易存在风险，请确保充分理解相关风险并谨慎操作。