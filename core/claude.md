# Core 模块架构文档

## 📋 概述

Core模块是ProCryptoTrader量化交易系统的核心业务逻辑层，实现了数据管理、策略开发、回测引擎、交易执行等核心功能。

## 🏗️ 模块架构

### 目录结构
```
core/
├── data/                   # 数据管理层
│   ├── data_fetcher.py    # 数据获取服务
│   ├── data_manager.py    # 数据管理器
│   ├── data_loader.py     # 数据加载器
│   ├── data_processor.py  # 数据处理器
│   ├── data_storage.py    # 数据存储
│   ├── data_service.py    # 数据服务
│   ├── data_validator.py  # 数据验证器
│   └── repositories/      # 数据仓储层
│       ├── base_repository.py
│       ├── ohlcv_repository.py
│       ├── metadata_repository.py
│       ├── cache_repository.py
│       └── data_factory.py
├── strategy/               # 策略开发层
│   ├── base_strategy.py   # 策略基类
│   ├── grid_strategy.py    # 网格策略
│   ├── martingale_strategy.py  # 马丁格尔策略
│   ├── dual_ma_strategy.py    # 双均线策略
│   ├── enhanced_base_strategy.py  # 增强基类
│   ├── enhanced_ma_strategy.py     # 增强均线策略
│   ├── high_frequency_breakout.py  # 🔥 高频突破策略 (最新)
│   ├── tick_breakout_detector.py   # 🔥 Tick级别突破检测器 (最新)
│   ├── traditional_grid_strategy.py # 传统网格策略
│   └── [其他网格策略变体]
├── backtest/               # 回测引擎
│   ├── backtester.py      # 回测引擎
│   ├── metrics.py         # 性能指标计算
│   └── report_generator.py # 报告生成器
├── trading/               # 交易执行层
│   ├── fast_execution.py # 🔥 快速执行引擎 (最新)
│   ├── order_manager.py  # 订单管理
│   └── position_manager.py # 持仓管理
├── exchange/              # 交易所接口
│   ├── base_exchange.py   # 基础交易所接口
│   ├── binance_api.py     # 币安API
│   └── okx_api.py         # OKX API
├── live/                  # 实盘交易
│   ├── live_trader.py     # 实盘交易引擎
│   ├── high_frequency_trader.py # 🔥 高频交易器 (最新)
│   └── config_loader.py   # 配置加载器
├── services/              # 服务层
│   ├── execution_service.py # 执行服务
│   ├── signal_service.py   # 信号服务
│   ├── strategy_service.py # 策略服务
│   └── position_service.py # 持仓服务
├── utils/                  # 工具层
│   ├── logger.py          # 日志系统
│   ├── config.py          # 配置管理
│   ├── risk_manager.py   # 风险管理
│   ├── risk_tools.py      # 风险工具
│   └── cache.py           # 缓存系统
├── interfaces/            # 接口定义
│   ├── data_interfaces.py # 数据接口
│   ├── trading_interfaces.py # 交易接口
│   ├── strategy_interfaces.py # 策略接口
│   └── risk_interfaces.py # 风险接口
└── models/                 # 数据模型
    ├── order.py           # 订单模型
    ├── position.py        # 持仓模型
    ├── signal.py          # 信号模型
    ├── trade.py           # 交易模型
    ├── risk.py            # 风险模型
    └── __init__.py        # 模型导出
```

## 🔄 模块间交互关系

### 数据流向图
```
外部数据源 → DataFetcher → DataManager → Strategy → Signal → RiskManager → Exchange → Order → Position
     ↓           ↓            ↓         ↓       ↓           ↓         ↓          ↓
     原始数据    数据处理    数据管理    策略分析   信号生成   风险验证   订单执行   持仓管理
```

### 依赖层次
```
应用层 (examples, scripts, tests)
    ↓
业务逻辑层 (strategy, backtest, live, trading, services)
    ↓
数据访问层 (data, repositories)
    ↓
基础设施层 (exchange, utils, cache)
    ↓
模型层 (models, interfaces)
```

## 📊 核心组件详解

### Data模块 (core/data/)

**职责**: 统一的数据获取、存储、管理和处理

**核心类**:
- `DataFetcher`: 从交易所API获取原始数据
- `DataManager`: 数据的统一管理接口
- `DataLoader`: 加载和预处理数据
- `DataProcessor`: 数据清洗和特征工程
- `DataStorage`: 数据持久化存储
- `DataValidator`: 数据质量验证

**仓储模式实现**:
- `BaseRepository`: 仓储抽象基类
- `OHLCVRepository`: K线数据仓储
- `MetadataRepository`: 元数据仓储
- `CacheRepository`: 缓存数据仓储
- `DataRepositoryFactory`: 仓储工厂

**设计特点**:
- 支持多交易所、多时间框架
- 实现仓储模式，解耦数据存储逻辑
- 集成缓存机制，提升访问性能
- 完整的数据验证和质量检查

### Strategy模块 (core/strategy/)

**职责**: 交易策略的开发和执行框架

**架构设计**:
```python
BaseStrategy (抽象基类)
├── 计算技术指标
├── 生成交易信号
├── 更新策略状态
└── 风险控制

具体策略实现:
├── GridStrategy (网格策略)
├── MartingaleStrategy (马丁格尔策略)
├── DualMAStrategy (双均线策略)
└── [自定义策略]
```

**核心接口**:
- `generate_signals()`: 生成交易信号
- `calculate_indicators()`: 计算技术指标
- `update()`: 更新策略状态
- `initialize()`: 策略初始化

**信号系统**:
- **SignalType**: 标准化的信号类型枚举
- **Signal**: 统一的信号数据结构
- 支持多种信号优先级和元数据

### Backtest模块 (core/backtest/)

**职责**: 策略回测引擎，评估策略性能

**回测流程**:
1. 配置解析和验证
2. 历史数据加载
3. 策略初始化
4. 时间序列循环执行
5. 信号生成和执行
6. 持仓和资金管理
7. 性能指标计算
8. 报告生成

**核心类**:
- `Backtester`: 主回测引擎
- `BacktestConfig`: 回测配置类
- `MetricsCalculator`: 性能指标计算器
- `ReportGenerator`: 报告生成器

**性能指标**:
- 收益率 (总收益、年化收益)
- 风险指标 (最大回撤、夏普比率)
- 交易统计 (交易次数、胜率、平均持仓时间)

### Trading模块 (core/trading/ + core/services/)

**职责**: 交易执行和持仓管理

**执行服务架构**:
```python
ExecutionService (总控制)
├── SignalService (信号处理)
├── OrderManager (订单管理)
├── PositionManager (持仓管理)
└── PositionService (持仓服务)
```

**核心功能**:
- 信号到订单的转换
- 订单生命周期管理
- 实时持仓跟踪
- 风险控制和止损止盈
- 交易执行统计

### Exchange模块 (core/exchange/)

**职责**: 统一的交易所API接口

**适配器模式**:
```python
BaseExchange (抽象接口)
├── place_order() / cancel_order()
├── get_balance() / get_positions()
├── get_order_status() / get_symbol_info()
└── get_ohlcv()

具体实现:
├── BinanceAPI (币安)
└── OKXAPI (OKX)
```

**特点**:
- 统一的API接口设计
- 支持多种订单类型
- 完整的错误处理机制
- 连接管理和重试逻辑

### Utils模块 (core/utils/)

**职责**: 基础设施和工具类

**核心组件**:
- `Logger`: 结构化日志系统
- `ConfigLoader`: 配置文件管理
- `RiskManager`: 风险管理核心
- `Cache`: 分布式缓存系统
- `RiskTools`: 风险计算工具

**特性**:
- 支持多种日志级别和输出
- 环境变量支持
- 完整的风险指标计算
- Redis和内存缓存
- 统计学风险工具

## 🎯 设计模式和原则

### 应用的设计模式

1. **工厂模式**: DataRepositoryFactory, StrategyFactory
2. **策略模式**: BaseStrategy抽象类
3. **适配器模式**: BaseExchange接口
4. **单例模式**: ServiceContainer全局容器
5. **仓储模式**: Repository抽象层
6. **依赖注入**: ServiceContainer IoC容器
7. **装饰器模式**: cache_decorators缓存装饰器
8. **命令模式**: 交易订单的封装

### RIPER-5原则

1. **Risk First (风险优先)**: 多层次风险控制
2. **Integration Minimal (最小侵入)**: 松耦合设计
3. **Predictability (可预期性)**: 标准化数据模型
4. **Expandability (可扩展性)**: 插件化架构
5. **Realistic Evaluation (真实可评估)**: 完整性能指标

## 🔧 配置和使用

### 环境配置
- 支持YAML配置文件
- 环境变量覆盖
- 配置验证和类型检查

### 日志配置
- 结构化日志输出
- 多级别日志支持
- 文件和控制台输出

### 缓存配置
- Redis分布式缓存
- 内存缓存优化
- 缓存策略配置

## 📈 性能优化

### 数据层优化
- 向量化计算 (pandas/numpy)
- 智能缓存机制
- 批量数据处理
- 数据压缩存储

### 计算层优化
- 并发数据处理
- 算法优化
- 内存管理优化

### 网络优化
- 连接池管理
- 请求批量处理
- 超时和重试机制

## 🛡️ 安全和风险

### 数据安全
- API密钥安全管理
- 数据传输加密
- 访问控制和权限管理

### 交易风险控制
- 多层次风险验证
- 实时监控和预警
- 止损止盈机制
- 仓位和杠杆限制

### 系统稳定性
- 完善的异常处理
- 容错和恢复机制
- 健康检查和监控

## 🔌 扩展指南

### 新增交易所
1. 实现BaseExchange接口
2. 添加到ExchangeFactory
3. 更新配置文件

### 新增策略
1. 继承BaseStrategy类
2. 实现必要的方法
3. 注册到策略工厂

### 新增数据源
1. 实现DataFetcher接口
2. 添加数据格式转换器
3. 集成到DataFactory

## 📚 相关文档

- [数据层详细文档](./data/claude.md)
- [策略开发指南](./strategy/claude.md)
- [回测引擎文档](./backtest/claude.md)
- [交易执行文档](./trading/claude.md)
- [模型层文档](./models/claude.md)
- [接口定义文档](./interfaces/claude.md)