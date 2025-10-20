# Crypto Quant Framework

## 一、项目概述
本项目旨在构建一个适用于加密货币市场的通用量化交易框架，涵盖行情获取、策略执行、回测评估及实盘运行。系统设计遵循 **RIPER-5 原则**：
- Risk first（风险优先）
- Integration minimal（最小侵入）
- Predictability（可预期性）
- Expandability（可扩展性）
- Realistic evaluation（真实可评估）

## 二、项目结构
```
crypto_quant_framework/
│
├── core/                          # 核心模块
│   ├── data/                      # 数据模块
│   │   ├── data_fetcher.py        # 使用 ccxt 获取行情数据
│   │   ├── data_manager.py        # 数据缓存与存储管理
│   │   └── data_loader.py         # 从本地加载K线数据
│   │
│   ├── exchange/                  # 交易接口模块
│   │   ├── base_exchange.py       # 自定义交易所接口标准定义
│   │   ├── binance_api.py         # Binance 交易接口实现
│   │   └── okx_api.py             # OKX 交易接口实现
│   │
│   ├── strategy/                  # 策略模块
│   │   ├── base_strategy.py       # 策略基类（信号生成接口）
│   │   ├── martingale_strategy.py # 马丁策略实现
│   │   ├── grid_strategy.py       # 网格策略实现
│   │   └── custom_factors/        # 用户自定义因子目录
│   │
│   ├── backtest/                  # 回测模块
│   │   ├── backtester.py          # 回测引擎核心类
│   │   ├── metrics.py             # 绩效评估指标
│   │   └── report_generator.py    # 回测报告生成
│   │
│   ├── live/                      # 实盘交易模块
│   │   ├── live_trader.py         # 实盘运行主控制器
│   │   └── config_loader.py       # 实盘配置读取
│   │
│   ├── utils/                     # 工具模块
│   │   ├── logger.py              # 日志系统
│   │   ├── config.py              # 配置文件解析
│   │   └── risk_control.py        # 风控工具类
│   │
│   └── analysis/                  # 分析模块
│       ├── trade_analyzer.py      # 交易结果分析
│       ├── performance_plot.py    # 可视化绘图
│       └── factor_analysis.py     # 因子效果评估
│
├── configs/                       # 配置文件目录
│   ├── backtest_config.yaml       # 回测配置文件
│   ├── live_config.yaml           # 实盘运行配置
│   └── logging_config.yaml        # 日志配置
│
├── tests/                         # 单元测试目录
│   ├── test_data.py
│   ├── test_strategy.py
│   ├── test_backtest.py
│   ├── test_exchange.py
│   └── test_live.py
│
├── examples/                      # 示例脚本目录
│   ├── run_backtest.py
│   ├── run_live.py
│   └── example_strategy.py
│
├── docs/                          # 文档目录
│   └── design.md                  # 详细设计文档（本文件）
│
├── requirements.txt               # 依赖库清单
├── README.md                      # 项目说明文件
└── setup.py                       # 安装脚本
```

## 三、核心模块设计

### 1. 数据模块（core/data）
- **data_fetcher.py**：通过 `ccxt` 获取实时与历史K线数据。
- **data_manager.py**：管理本地数据存储与更新，支持多时间框架（1m/5m/1d等）。K 线数据：parquet（列式压缩、查询高效），按 symbol/timeframe 分文件夹管理。
- **data_loader.py**：回测阶段加载已缓存的K线数据。

### 2. 交易接口模块（core/exchange）
- **base_exchange.py**：定义标准接口，包括下单、撤单、获取账户资产、获取订单状态等。
- **各交易所实现类**（如 `binance_api.py`、`okx_api.py`）继承该标准接口，封装各交易所API。

### 3. 策略模块（core/strategy）
- **base_strategy.py**：定义策略基类：这些基础策略只负责生成信号（何时加仓、何时减仓、每次加仓倍数/网格位置），而不直接执行下单。风控层可在得到 signal 后决定是否执行。
  ```python
  class BaseStrategy:
      def __init__(self, config):
          self.config = config

      def generate_signals(self, df):
          """根据行情DataFrame返回买卖信号。"""
          raise NotImplementedError
  ```
- **martingale_strategy.py**：实现马丁格尔加仓逻辑。
核心思想：在亏损时按预设比例增加仓位以降低平均持仓价，直到达到止损或上限。
关键配置：
base_size（首仓大小或占资金比例）
max_layers（最大加仓次数）
multiplier（每次加仓倍数）
add_on_loss_pct（触发加仓的亏损阈值，例如 -2%）
max_total_exposure（对单一资产的最大敞口）
stop_loss_pct（整体止损触发点）
策略行为：
当首次开仓满足信号时创建首仓 signal。
如果持仓浮亏达到 add_on_loss_pct，返回 increase signal，大小 = 上一次 * multiplier（受 max_layers 与最大敞口限制）。
如果达到止损，返回 close 信号。
- **grid_strategy.py**：实现区间网格交易逻辑。
核心思想：在价格区间内布置固定价格间距的买卖挂单，借助波动获取收益（更像做市或趋势区间策略）。
关键配置：
grid_upper/ lower（网格上限/下限）
grid_steps（格数）
base_order_size（每格挂单大小）
rebalance_interval（重建网格的频率）
max_exposure_per_symbol
策略行为：
根据当前价格与网格，生成 open 或 close 信号（闭环：买低卖高）。
可以和挂单管理器（engine 中）协同：网格策略只提供目标网格状态，broker 负责实际挂单/撤单。
- **custom_factors/**：为后续新因子提供插入式支持。

### 4. 回测模块（core/backtest）
关键需求：可复现、高性能、记录详尽。
输入：本地 K 线（parquet/csv/sqlite），策略类实例或策略集合，回测参数（初始资金、杠杆、滑点模型、手续费、交易对列表、时间段）。
时间循环方式：以最小选定的 timeframe 顺序驱动（例如 1m）。对于多策略/多时间框架，使用事件队列（每根 candle 发出 on_candle 事件）。
每个时间步的步骤：
加载当前 candle 数据，传给策略 on_candle，获得 signals。
RiskManager.validate_order 过滤信号。
Broker.execute 提交并模拟成交，返回 trade record。
更新账户快照、持仓、手续费、资金曲线。
保存交易日志与逐时账户快照（用于回测后计算指标）。
手续费与滑点：可配置成比例费率或阶梯，滑点模型支持固定滑点、按成交量比例或随机噪声（需可控随机种子）。
事件与回放：保存 signal -> order -> execution 三套日志，支持回放到可视化工具（如 notebook / 本地 plot）。
- **backtester.py**：负责执行策略在历史数据上的回测。
- **metrics.py**：计算常用指标（年化收益率、最大回撤、Sharpe、胜率等）。
- **report_generator.py**：生成回测报告（支持HTML/PDF/Markdown格式）。

### 5. 实盘模块（core/live）
读取 live.yaml，支持多个策略同时运行（每个策略可以配置其监听的 symbols 与 timeframe）。
使用 ExchangeAdapter 与交易所通讯（ccxt 实现）。
关键功能：
心跳与重连策略（对 API 超时/断连做降压）。
风控守门（每次下单前校验、最大单日亏损限额、风控断路器）。
异常保护：订单未成交多次尝试/撤单策略。
日志与告警（重要事件即时告警）。
审计：保存所有原始 exchange 响应以便事后核查。
最小侵入原则：对于接入新交易所，只需要实现 ExchangeAdapter 的方法，不必修改策略或引擎代码。
- **live_trader.py**：根据配置文件运行多策略多币种实盘机器人。
- **config_loader.py**：解析 `live_config.yaml`，自动实例化策略与交易所连接。

### 6. 分析模块（core/analysis）
- **trade_analyzer.py**：对交易记录进行盈亏分布、胜率分析。
- **performance_plot.py**：生成资金曲线、回撤曲线等图表。
- **factor_analysis.py**：用于评估因子表现与贡献度。

### 7. 风控与工具模块（core/utils）
下单前校验：RiskManager.validate_order（单笔仓位、累积仓位、对冲冲突、黑名单）。
全局断路器：当回撤、日亏损或连续 N 次亏损超过阈值时，自动停止策略或发出告警。
逐笔止损/止盈：建议策略在 meta 或 signal 中传入止损位与止盈位，broker 支持 OCO/市价强行平等。
资金隔离：每个策略或每个 symbol 可使用独立子账户或模拟子账户，避免一个策略将全部资金耗尽。
最小订单/精度处理：对接不同交易所时，通过 ExchangeAdapter 提供价格/数量最小精度处理，避免下单失败。
审计日志：所有 API 请求/响应与回测撮合结果都写入持久化日志。
- **risk_control.py**：实现统一风控逻辑（最大持仓限制、止盈止损等）。
- **logger.py**：统一日志格式与等级。
- **config.py**：封装配置加载（YAML/JSON）。

## 四、配置文件设计

### 1. 回测配置（`backtest_config.yaml`）
```yaml
start_date: '2023-01-01'
end_date: '2023-12-31'
initial_balance: 10000
fee_rate: 0.001
strategy: 'GridStrategy'
params:
  grid_spacing: 0.01
  grid_levels: 10
symbols: ['BTC/USDT', 'ETH/USDT']
timeframes: ['1h']
```

### 2. 实盘配置（`live_config.yaml`）
```yaml
exchanges:
  binance:
    api_key: 'xxxx'
    api_secret: 'xxxx'

strategies:
  - name: 'Martingale'
    symbols: ['BTC/USDT']
    timeframe: '1m'
  - name: 'Grid'
    symbols: ['ETH/USDT', 'SOL/USDT']
    timeframe: '5m'
```

## 五、开发阶段规划

### 阶段 1：框架搭建
- 建立目录结构与依赖环境
- 实现数据获取与交易接口基类

### 阶段 2：策略与回测模块
- 实现策略基类、网格、马丁策略
- 完成回测引擎与报告系统

### 阶段 3：实盘交易模块
- 实现多策略多币种并行执行
- 集成统一风控系统

### 阶段 4：分析与优化
- 构建回测与实盘结果分析模块
- 增强风险监控与日志追踪

## 六、扩展方向
- 引入强化学习或机器学习因子。
- 实现自动调参与策略组合优化。
- 添加交易监控与报警系统（Telegram/Discord 通知）。

---

本框架的设计目标是 **模块化、可插拔、低耦合、高稳定性**，确保从研究到实盘全流程闭环。
