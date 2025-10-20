# 实盘交易系统使用指南

本指南将帮助您了解如何使用ProCryptoTrader的实盘交易系统，安全地进行自动化交易。

## 实盘交易系统概述

实盘交易系统是量化交易的核心执行工具，它连接到交易所API，根据策略信号自动执行交易。ProCryptoTrader的实盘交易系统支持多种交易所，提供风险控制、订单管理、持仓监控等功能，确保交易的安全和稳定。

## 安全注意事项

在开始实盘交易之前，请务必注意以下安全事项：

1. **API密钥安全**：
   - 使用只读和交易权限的最小化API密钥
   - 不要将API密钥提交到代码仓库
   - 定期更换API密钥
   - 使用IP白名单限制API访问

2. **资金安全**：
   - 从小额资金开始测试
   - 设置合理的风险限制
   - 不要投入超过可承受损失的资金
   - 定期检查账户余额和持仓

3. **策略安全**：
   - 在模拟环境中充分测试策略
   - 设置合理的止损和止盈
   - 监控策略执行情况
   - 准备紧急停止机制

## 实盘交易流程

### 1. 配置交易所API

首先，需要配置交易所API：

```python
# config/exchange_config.yaml
exchange:
  name: "binance"  # 交易所名称
  sandbox: false   # 是否使用沙盒环境
  
  # API密钥（建议使用环境变量）
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  
  # API设置
  timeout: 10      # 请求超时时间（秒）
  retries: 3       # 重试次数
  rate_limit: 1200 # 请求频率限制（请求/分钟）

# 交易对设置
symbols:
  - "BTC/USDT"
  - "ETH/USDT"
  
# 风控设置
risk:
  max_position_size: 0.1  # 最大持仓比例
  max_drawdown: 0.1       # 最大回撤
  daily_loss_limit: 0.05  # 日亏损限制
```

### 2. 创建交易策略

接下来，创建或选择交易策略：

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

### 3. 配置交易系统

设置交易系统的参数：

```python
from core.trading.trader import Trader
from core.utils.risk_manager import RiskManager
from core.trading.order_manager import OrderManager
from core.trading.position_manager import PositionManager

# 创建风险管理器
risk_manager = RiskManager({
    "max_position_size": 0.1,    # 最大持仓比例
    "max_drawdown": 0.1,         # 最大回撤
    "daily_loss_limit": 0.05,    # 日亏损限制
    "max_orders_per_minute": 10  # 每分钟最大订单数
})

# 创建订单管理器
order_manager = OrderManager({
    "default_type": "limit",     # 默认订单类型
    "retry_attempts": 3,         # 重试次数
    "order_timeout": 60,         # 订单超时时间（秒）
    "partial_fill_threshold": 0.9 # 部分成交阈值
})

# 创建持仓管理器
position_manager = PositionManager({
    "max_positions": 5,          # 最大持仓数量
    "position_size_method": "fixed", # 持仓大小计算方法
    "default_size": 0.01         # 默认持仓大小
})

# 创建交易器
trader = Trader(
    exchange_config="config/exchange_config.yaml",
    strategy=strategy,
    risk_manager=risk_manager,
    order_manager=order_manager,
    position_manager=position_manager
)
```

### 4. 运行模拟交易

在实盘交易前，建议先运行模拟交易：

```python
# 运行模拟交易
trader.run_paper_trading(
    duration="1d",  # 运行时间
    symbols=["BTC/USDT"],  # 交易对
    timeframe="1h"   # 时间框架
)
```

### 5. 运行实盘交易

确认策略和配置无误后，可以开始实盘交易：

```python
# 运行实盘交易
trader.run_live_trading(
    symbols=["BTC/USDT"],  # 交易对
    timeframe="1h"   # 时间框架
)
```

## 交易系统配置

### 完整配置文件

可以使用完整的配置文件进行交易：

```yaml
# config/live_trading_config.yaml
# 交易所设置
exchange:
  name: "binance"
  sandbox: false
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  timeout: 10
  retries: 3
  rate_limit: 1200

# 交易对设置
symbols:
  - "BTC/USDT"
  - "ETH/USDT"

# 策略设置
strategy:
  name: "GridStrategy"
  params:
    grid_size: 0.01
    grid_levels: 10
    order_size: 0.01
    take_profit: 0.02
    stop_loss: 0.05

# 交易设置
trading:
  timeframe: "1h"
  order_type: "limit"
  retry_attempts: 3
  order_timeout: 60
  partial_fill_threshold: 0.9

# 风控设置
risk:
  max_position_size: 0.1
  max_drawdown: 0.1
  daily_loss_limit: 0.05
  max_orders_per_minute: 10
  emergency_stop: true

# 持仓管理
position:
  max_positions: 5
  position_size_method: "fixed"
  default_size: 0.01

# 监控设置
monitoring:
  enabled: true
  log_level: "INFO"
  notifications:
    email:
      enabled: false
    telegram:
      enabled: false
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"

# 数据设置
data:
  save_trades: true
  save_orders: true
  save_positions: true
  backup_interval: 3600  # 备份间隔（秒）
```

使用配置文件运行交易：

```python
from core.trading.trader import Trader
from core.utils.config import ConfigParser

# 读取配置
parser = ConfigParser()
config = parser.read_config("config/live_trading_config.yaml")

# 创建交易器
trader = Trader(config)

# 运行模拟交易
trader.run_paper_trading()

# 运行实盘交易
# trader.run_live_trading()
```

## 风险管理

### 仓位管理

系统提供多种仓位管理方法：

```python
from core.trading.position_manager import PositionManager

# 固定仓位管理
position_manager = PositionManager({
    "position_size_method": "fixed",
    "default_size": 0.01
})

# 百分比仓位管理
position_manager = PositionManager({
    "position_size_method": "percentage",
    "percentage": 0.1  # 每次交易使用账户资金的10%
})

# 波动率调整仓位管理
position_manager = PositionManager({
    "position_size_method": "volatility",
    "base_size": 0.01,
    "volatility_target": 0.15,  # 目标年化波动率
    "lookback_period": 20       # 波动率计算周期
})

# 凯利准则仓位管理
position_manager = PositionManager({
    "position_size_method": "kelly",
    "win_rate": 0.55,          # 胜率
    "avg_win": 0.02,           # 平均盈利
    "avg_loss": 0.01,          # 平均亏损
    "kelly_fraction": 0.25     # 凯利分数（降低风险）
})
```

### 止损管理

系统提供多种止损管理方法：

```python
from core.utils.risk_manager import RiskManager

# 固定百分比止损
risk_manager = RiskManager({
    "stop_loss_method": "percentage",
    "stop_loss_percentage": 0.05  # 5%止损
})

# 追踪止损
risk_manager = RiskManager({
    "stop_loss_method": "trailing",
    "trailing_percentage": 0.02,  # 2%追踪止损
    "activation_percentage": 0.01  # 1%激活追踪止损
})

# ATR止损
risk_manager = RiskManager({
    "stop_loss_method": "atr",
    "atr_period": 14,        # ATR周期
    "atr_multiplier": 2.0    # ATR倍数
})

# 布林带止损
risk_manager = RiskManager({
    "stop_loss_method": "bollinger",
    "bb_period": 20,         # 布林带周期
    "bb_std": 2.0            # 标准差
})
```

### 资金管理

系统提供多种资金管理方法：

```python
from core.utils.risk_manager import RiskManager

# 固定金额管理
risk_manager = RiskManager({
    "capital_method": "fixed",
    "fixed_amount": 1000  # 每次交易固定金额
})

# 固定比例管理
risk_manager = RiskManager({
    "capital_method": "percentage",
    "percentage": 0.1  # 每次交易使用账户资金的10%
})

# 风险平价管理
risk_manager = RiskManager({
    "capital_method": "risk_parity",
    "risk_per_trade": 0.02  # 每笔交易风险2%
})

# 凯利准则管理
risk_manager = RiskManager({
    "capital_method": "kelly",
    "win_rate": 0.55,          # 胜率
    "avg_win": 0.02,           # 平均盈利
    "avg_loss": 0.01,          # 平均亏损
    "kelly_fraction": 0.25     # 凯利分数（降低风险）
})
```

## 订单管理

### 订单类型

系统支持多种订单类型：

```python
from core.trading.order_manager import OrderManager

# 创建订单管理器
order_manager = OrderManager()

# 限价单
order_manager.create_limit_order(
    symbol="BTC/USDT",
    side="buy",
    amount=0.01,
    price=50000
)

# 市价单
order_manager.create_market_order(
    symbol="BTC/USDT",
    side="sell",
    amount=0.01
)

# 止损单
order_manager.create_stop_order(
    symbol="BTC/USDT",
    side="sell",
    amount=0.01,
    stop_price=48000
)

# 止盈单
order_manager.create_take_profit_order(
    symbol="BTC/USDT",
    side="sell",
    amount=0.01,
    take_profit_price=52000
)

# 冰山单
order_manager.create_iceberg_order(
    symbol="BTC/USDT",
    side="buy",
    amount=0.1,
    price=50000,
    iceberg_visible_size=0.01
)

# TWAP订单
order_manager.create_twap_order(
    symbol="BTC/USDT",
    side="buy",
    amount=0.1,
    duration=3600,  # 持续时间（秒）
    num_slices=10   # 切片数量
)
```

### 订单状态监控

系统提供订单状态监控功能：

```python
# 获取订单状态
order_status = order_manager.get_order_status(order_id)

# 取消订单
order_manager.cancel_order(order_id)

# 获取未成交订单
open_orders = order_manager.get_open_orders()

# 获取历史订单
order_history = order_manager.get_order_history(
    symbol="BTC/USDT",
    limit=100
)
```

## 持仓管理

### 持仓查询

系统提供持仓查询功能：

```python
from core.trading.position_manager import PositionManager

# 创建持仓管理器
position_manager = PositionManager()

# 获取所有持仓
positions = position_manager.get_all_positions()

# 获取特定交易对持仓
btc_position = position_manager.get_position("BTC/USDT")

# 获取持仓价值
position_value = position_manager.get_position_value("BTC/USDT")

# 获取未实现盈亏
unrealized_pnl = position_manager.get_unrealized_pnl("BTC/USDT")

# 获取已实现盈亏
realized_pnl = position_manager.get_realized_pnl("BTC/USDT")
```

### 持仓调整

系统提供持仓调整功能：

```python
# 增加持仓
position_manager.increase_position(
    symbol="BTC/USDT",
    amount=0.01,
    price=50000
)

# 减少持仓
position_manager.decrease_position(
    symbol="BTC/USDT",
    amount=0.01,
    price=52000
)

# 平仓
position_manager.close_position("BTC/USDT")

# 调整止损
position_manager.adjust_stop_loss(
    symbol="BTC/USDT",
    stop_loss=48000
)

# 调整止盈
position_manager.adjust_take_profit(
    symbol="BTC/USDT",
    take_profit=52000
)
```

## 监控与通知

### 交易监控

系统提供交易监控功能：

```python
from core.trading.monitor import TradingMonitor

# 创建交易监控器
monitor = TradingMonitor()

# 启动监控
monitor.start_monitoring()

# 获取账户余额
balance = monitor.get_balance()

# 获取账户信息
account_info = monitor.get_account_info()

# 获取服务器时间
server_time = monitor.get_server_time()

# 检查系统状态
system_status = monitor.check_system_status()
```

### 通知系统

系统提供多种通知方式：

```python
from core.trading.notifications import NotificationManager

# 创建通知管理器
notification_manager = NotificationManager()

# 邮件通知
notification_manager.enable_email({
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your_email@gmail.com",
    "password": "your_password",
    "from_email": "your_email@gmail.com",
    "to_emails": ["recipient1@gmail.com", "recipient2@gmail.com"]
})

# Telegram通知
notification_manager.enable_telegram({
    "bot_token": "your_bot_token",
    "chat_id": "your_chat_id"
})

# 发送通知
notification_manager.send_notification(
    message="交易信号：买入 BTC/USDT @ 50000",
    level="info"
)

# 发送紧急通知
notification_manager.send_emergency_notification(
    message="紧急：系统检测到异常交易活动",
    level="critical"
)
```

## 数据记录与备份

### 交易记录

系统自动记录所有交易活动：

```python
from core.trading.data_recorder import TradingDataRecorder

# 创建交易数据记录器
recorder = TradingDataRecorder()

# 启动记录
recorder.start_recording()

# 记录交易
recorder.record_trade({
    "symbol": "BTC/USDT",
    "side": "buy",
    "amount": 0.01,
    "price": 50000,
    "timestamp": "2023-01-01 00:00:00",
    "order_id": "12345"
})

# 记录订单
recorder.record_order({
    "symbol": "BTC/USDT",
    "side": "buy",
    "amount": 0.01,
    "price": 50000,
    "status": "filled",
    "timestamp": "2023-01-01 00:00:00",
    "order_id": "12345"
})

# 记录持仓
recorder.record_position({
    "symbol": "BTC/USDT",
    "amount": 0.01,
    "entry_price": 50000,
    "current_price": 51000,
    "unrealized_pnl": 10,
    "timestamp": "2023-01-01 00:00:00"
})
```

### 数据备份

系统提供数据备份功能：

```python
from core.trading.backup_manager import BackupManager

# 创建备份管理器
backup_manager = BackupManager({
    "backup_interval": 3600,  # 备份间隔（秒）
    "backup_location": "backups",  # 备份位置
    "max_backups": 10  # 最大备份数量
})

# 启动自动备份
backup_manager.start_auto_backup()

# 手动备份
backup_manager.create_backup()

# 恢复备份
backup_manager.restore_backup("backup_20230101_000000.zip")

# 清理旧备份
backup_manager.cleanup_old_backups()
```

## 紧急处理

### 紧急停止

系统提供紧急停止功能：

```python
from core.trading.emergency_handler import EmergencyHandler

# 创建紧急处理器
emergency_handler = EmergencyHandler()

# 紧急停止所有交易
emergency_handler.emergency_stop_all()

# 紧急平仓
emergency_handler.emergency_close_all_positions()

# 紧急取消所有订单
emergency_handler.emergency_cancel_all_orders()

# 设置紧急停止条件
emergency_handler.set_emergency_conditions({
    "max_drawdown": 0.15,  # 最大回撤15%
    "max_daily_loss": 0.1,  # 最大日亏损10%
    "max_position_loss": 0.05  # 最大持仓亏损5%
})
```

### 系统故障恢复

系统提供故障恢复功能：

```python
from core.trading.recovery_manager import RecoveryManager

# 创建恢复管理器
recovery_manager = RecoveryManager()

# 检查系统状态
system_status = recovery_manager.check_system_status()

# 恢复未完成订单
recovery_manager.recover_pending_orders()

# 恢复持仓状态
recovery_manager.recover_positions()

# 恢复交易状态
recovery_manager.recover_trading_state()
```

## 常见问题

### 1. API连接失败

可能原因：
- API密钥错误
- 网络连接问题
- 交易所服务器维护

解决方法：
- 检查API密钥是否正确
- 检查网络连接
- 查看交易所公告

### 2. 订单执行失败

可能原因：
- 余额不足
- 市场价格变动
- 交易限制

解决方法：
- 检查账户余额
- 调整订单价格
- 检查交易限制

### 3. 持仓管理错误

可能原因：
- 持仓数据不同步
- 订单状态更新延迟
- 系统故障

解决方法：
- 同步持仓数据
- 检查订单状态
- 重启系统

## 最佳实践

1. **小额开始**：从小额资金开始，逐步增加投入。
2. **充分测试**：在模拟环境中充分测试策略。
3. **风险控制**：设置合理的止损和仓位管理。
4. **监控系统**：实时监控交易活动和系统状态。
5. **定期备份**：定期备份交易数据和配置。
6. **应急预案**：准备紧急处理方案。

## 总结

实盘交易是量化交易的最终目标，但也是风险最高的环节。通过合理使用实盘交易系统，可以安全地执行交易策略，实现自动化交易。但需要注意的是，市场风险始终存在，任何策略都无法保证盈利，因此需要持续监控和调整策略，控制风险，保护资金安全。