# 运维手册 (Runbook)

本文档提供ProCryptoTrader系统的部署、监控、故障排查和维护指南。

## 目录

- [系统概述](#系统概述)
- [部署流程](#部署流程)
- [监控和告警](#监控和告警)
- [日常维护](#日常维护)
- [常见问题和解决方案](#常见问题和解决方案)
- [应急处理](#应急处理)
- [回滚流程](#回滚流程)

---

## 系统概述

### 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      ProCryptoTrader                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  数据获取层   │  │   策略层     │  │   执行层     │      │
│  │              │  │              │  │              │      │
│  │ • WebSocket  │  │ • 网格策略   │  │ • 订单管理   │      │
│  │ • REST API   │  │ • 突破策略   │  │ • 持仓管理   │      │
│  │ • 数据缓存   │  │ • 风险控制   │  │ • 风险监控   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                           │                                 │
│                  ┌────────┴────────┐                        │
│                  │  数据存储层     │                        │
│                  │                 │                        │
│                  │ • Parquet数据   │                        │
│                  │ • SQLite数据库  │                        │
│                  │ • 日志文件      │                        │
│                  └─────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 功能 | 状态监控 |
|------|------|----------|
| **WebSocket客户端** | 实时市场数据流 | 连接状态、消息延迟 |
| **策略引擎** | 信号生成和管理 | CPU使用率、内存占用 |
| **风险管理器** | 实时风险监控 | 持仓暴露、回撤水平 |
| **订单管理器** | 订单提交和跟踪 | 订单状态、成交率 |
| **数据存储** | Tick数据和K线数据 | 磁盘使用率、I/O性能 |

---

## 部署流程

### 前置准备

#### 1. 系统要求

```bash
# 检查Python版本
python --version  # >= 3.8

# 检查可用内存
free -h  # >= 4GB

# 检查磁盘空间
df -h    # >= 2GB可用
```

#### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/your-org/ProCryptoTrader.git
cd ProCryptoTrader

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 3. 配置环境

```bash
# 复制配置文件
cp .env.example .env
cp configs/live_config.yaml.example configs/live_config.yaml

# 编辑配置
nano .env
nano configs/live_config.yaml
```

**关键配置项**:

```yaml
# .env文件
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_SANDBOX=true  # 测试环境

# configs/live_config.yaml
basic:
  mode: "paper"  # 先使用paper模式测试
  initial_balance: 10000.0

trading:
  max_total_exposure_pct: 0.2
  signal_cooldown_seconds: 60
```

### 部署步骤

#### 阶段1: 模拟环境测试

```bash
# 1. 运行回测验证策略
python examples/backtest_example.py

# 2. 运行模拟交易
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode paper

# 3. 监控日志
tail -f logs/trader.log
```

#### 阶段2: 测试网环境

```bash
# 1. 修改配置启用测试网
# .env: BINANCE_SANDBOX=true

# 2. 运行小资金测试
python -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode live

# 3. 验证订单执行
# - 检查订单是否正确提交
# - 验证持仓更新
# - 确认风险控制生效
```

#### 阶段3: 生产环境部署

```bash
# 1. 使用systemd管理服务 (Linux)
sudo nano /etc/systemd/system/procrypto-trader.service
```

**systemd服务配置**:

```ini
[Unit]
Description=ProCryptoTrader Trading Bot
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/ProCryptoTrader
Environment="PATH=/home/trader/ProCryptoTrader/.venv/bin"
ExecStart=/home/trader/ProCryptoTrader/.venv/bin/python \
    -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode live
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# 2. 启动服务
sudo systemctl enable procrypto-trader
sudo systemctl start procrypto-trader

# 3. 检查服务状态
sudo systemctl status procrypto-trader

# 4. 查看日志
sudo journalctl -u procrypto-trader -f
```

#### 阶段4: 使用Supervisor (可选)

```bash
# 安装Supervisor
pip install supervisor

# 创建配置文件
sudo nano /etc/supervisor/conf.d/procrypto-trader.conf
```

**Supervisor配置**:

```ini
[program:procrypto-trader]
command=/home/trader/ProCryptoTrader/.venv/bin/python \
    -m core.live.high_frequency_trader \
    --config configs/hf_breakout_live_config.yaml \
    --mode live
directory=/home/trader/ProCryptoTrader
user=trader
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/procrypto-trader.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
```

```bash
# 重新加载配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动服务
sudo supervisorctl start procrypto-trader

# 查看状态
sudo supervisorctl status
```

---

## 监控和告警

### 关键监控指标

#### 1. 系统级监控

```bash
# CPU使用率
top -b -n 1 | grep python

# 内存使用
free -h

# 磁盘使用
df -h

# 网络连接
netstat -an | grep ESTABLISHED
```

#### 2. 应用级监控

**脚本: `scripts/monitor_system.py`**

```python
import psutil
import logging

def check_system_health():
    """检查系统健康状态"""
    # CPU使用率
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > 80:
        logging.warning(f"⚠️ CPU使用率过高: {cpu_percent}%")

    # 内存使用率
    memory = psutil.virtual_memory()
    if memory.percent > 85:
        logging.warning(f"⚠️ 内存使用率过高: {memory.percent}%")

    # 磁盘使用率
    disk = psutil.disk_usage('/')
    if disk.percent > 90:
        logging.error(f"🚨 磁盘空间不足: {disk.percent}%")

    return {
        'cpu': cpu_percent,
        'memory': memory.percent,
        'disk': disk.percent
    }

if __name__ == "__main__":
    health = check_system_health()
    print(f"系统状态: CPU={health['cpu']}%, 内存={health['memory']}%, 磁盘={health['disk']}%")
```

#### 3. 业务级监控

**监控指标**:

| 指标 | 正常范围 | 告警阈值 | 说明 |
|------|----------|----------|------|
| **WebSocket连接状态** | Connected | Disconnected > 30s | 数据流连接 |
| **订单响应延迟** | < 1s | > 2s | 从信号到订单提交 |
| **持仓暴露** | < 15% | > 20% | 总资金占用比例 |
| **日收益率** | -3% ~ +5% | < -3% | 单日盈亏 |
| **最大回撤** | < 10% | > 10% | 累计最大回撤 |
| **信号生成频率** | 10-30/小时 | < 5 或 > 50 | 策略活跃度 |

### 日志监控

#### 日志文件位置

```
logs/
├── trader.log              # 主交易日志
├── websocket.log           # WebSocket连接日志
├── strategy.log            # 策略执行日志
├── execution.log           # 订单执行日志
└── error.log              # 错误日志
```

#### 实时日志监控

```bash
# 监控主日志
tail -f logs/trader.log

# 监控错误日志
tail -f logs/error.log

# 过滤特定级别日志
tail -f logs/trader.log | grep ERROR

# 统计错误数量
grep -c ERROR logs/trader.log
```

#### 日志分析脚本

```bash
# 分析最近1小时的错误
grep "ERROR" logs/trader.log | \
    awk '$1 " " $2 > "'"$(date -d '1 hour ago' '+%Y-%m-%d %H')"'"' | \
    wc -l

# 统计信号生成频率
grep "信号生成" logs/strategy.log | \
    awk '{print $1}' | uniq -c
```

### 告警配置

#### Email告警

```python
# scripts/alert_email.py
import smtplib
from email.mime.text import MIMEText

def send_alert(subject: str, message: str):
    """发送告警邮件"""
    msg = MIMEText(message)
    msg['Subject'] = f"[ProCryptoTrader 告警] {subject}"
    msg['From'] = "alerts@procrypto.trader"
    msg['To'] = "admin@procrypto.trader"

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('alerts@procrypto.trader', 'password')
        server.send_message(msg)

# 使用示例
send_alert(
    "连接中断",
    "WebSocket连接已断开超过30秒，请检查网络连接！"
)
```

#### Webhook告警

```bash
# 使用curl发送webhook
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
    -H 'Content-Type: application/json' \
    -d '{"text": "⚠️ ProCryptoTrader告警: WebSocket连接断开"}'
```

---

## 日常维护

### 每日任务

#### 1. 晨检 (每天开盘前)

```bash
# 检查服务状态
sudo systemctl status procrypto-trader

# 检查日志是否有错误
grep -i "error\|exception\|failed" logs/trader.log | tail -20

# 检查磁盘空间
df -h | grep -E "/$|/home"

# 检查网络连接
ping -c 3 api.binance.com
```

#### 2. 日中监控 (每2-4小时)

```bash
# 查看实时日志
tail -100 logs/trader.log

# 检查持仓和盈亏
python -c "
from core.trading.position_manager import PositionManager
pm = PositionManager()
positions = pm.get_all_positions()
for pos in positions:
    print(f'{pos.symbol}: {pos.size} @ {pos.entry_price}')
"

# 检查信号生成情况
grep "信号生成" logs/strategy.log | tail -20
```

#### 3. 晚检 (每天收盘后)

```bash
# 备份数据
python scripts/backup_data.py

# 生成日报
python scripts/generate_daily_report.py

# 归档日志
mv logs/trader.log logs/archive/trader_$(date +%Y%m%d).log
```

### 每周任务

#### 1. 数据备份

```bash
# 备份交易数据
python scripts/backup_data.py --weekly

# 备份配置文件
tar -czf configs_backup_$(date +%Y%m%d).tar.gz configs/

# 上传到云存储 (可选)
aws s3 sync data/ s3://your-bucket/procrypto-data/
```

#### 2. 性能分析

```bash
# 分析回测结果
python scripts/analyze_backtest_performance.py

# 生成性能报告
python scripts/generate_performance_report.py --period week
```

#### 3. 策略评估

```bash
# 运行参数优化
python scripts/optimize_strategy_params.py

# 评估策略表现
python scripts/evaluate_strategy.py --config configs/live_config.yaml
```

### 每月任务

#### 1. 系统更新

```bash
# 更新依赖
pip install --upgrade -r requirements.txt

# 更新代码
git pull origin main

# 运行测试
pytest
```

#### 2. 数据清理

```bash
# 清理旧日志 (保留最近30天)
find logs/ -name "*.log" -mtime +30 -delete

# 清理旧Tick数据 (保留最近7天)
find data/tick/ -name "*.parquet" -mtime +7 -delete

# 压缩归档数据
find data/archive/ -name "*.csv" -mtime +90 -exec gzip {} \;
```

#### 3. 安全检查

```bash
# 检查API密钥有效期
python scripts/check_api_key_expiry.py

# 更新密钥 (如需要)
nano .env

# 审计访问日志
sudo grep "procrypto-trader" /var/log/auth.log
```

---

## 常见问题和解决方案

### 1. WebSocket连接问题

#### 症状

```
ERROR: WebSocket连接失败
ERROR: 无法接收市场数据
```

#### 诊断步骤

```bash
# 1. 检查网络连接
ping api.binance.com

# 2. 检查防火墙规则
sudo iptables -L | grep 443

# 3. 查看详细错误日志
tail -50 logs/websocket.log
```

#### 解决方案

**方案1: 检查API配置**

```python
# 验证API密钥
from core.exchange.binance_api import BinanceAPI

api = BinanceAPI(
    api_key="your_key",
    api_secret="your_secret",
    sandbox=True
)

# 测试连接
status = api.test_connectivity()
print(f"连接状态: {status}")
```

**方案2: 重启WebSocket**

```bash
# 重启服务
sudo systemctl restart procrypto-trader

# 或手动重启连接
python scripts/restart_websocket.py
```

**方案3: 切换备用节点**

```yaml
# configs/live_config.yaml
websocket:
  base_url: "wss://stream.binance.com:9443"  # 主节点
  # 备用节点
  fallback_urls:
    - "wss://stream.binance.vision"
    - "wss://stream.binance.cloud"
```

### 2. 订单执行失败

#### 症状

```
ERROR: 订单提交失败
ERROR: 余额不足
ERROR: 订单被拒绝
```

#### 诊断步骤

```bash
# 1. 检查账户余额
python -c "
from core.exchange.binance_api import BinanceAPI
api = BinanceAPI(...)
balance = api.get_balance()
print(f'USDT余额: {balance.get(\"USDT\", 0)}')
"

# 2. 检查订单日志
tail -50 logs/execution.log

# 3. 检查风险限制
python scripts/check_risk_limits.py
```

#### 解决方案

**方案1: 检查余额**

```python
# 确保有足够余额
from core.exchange.binance_api import BinanceAPI
api = BinanceAPI(...)

# 查看可用余额
available = api.get_available_balance("USDT")
if available < required_amount:
    print(f"⚠️ 余额不足: 需要{required_amount}, 可用{available}")
```

**方案2: 调整订单大小**

```yaml
# configs/live_config.yaml
trading:
  default_position_size_usdt: 50  # 减小订单大小
  min_trade_value_usdt: 10
  max_trade_value_usdt: 200
```

**方案3: 检查风控参数**

```python
from core.utils.risk_manager import RiskManager

risk_mgr = RiskManager()
risk_mgr.max_position_size = 0.05  # 限制单笔最大5%
risk_mgr.max_total_exposure = 0.2  # 限制总暴露20%
```

### 3. 内存泄漏

#### 症状

```
系统内存使用持续增长
进程最终被OOM Killer杀死
```

#### 诊断步骤

```bash
# 1. 监控内存使用
watch -n 5 'ps aux | grep python'

# 2. 使用内存分析工具
mprof run examples/backtest_example.py
mprof plot

# 3. 查看详细内存统计
cat /proc/$(pidof python)/status | grep -E "VmSize|VmRSS"
```

#### 解决方案

**方案1: 限制数据缓存大小**

```python
# core/cache/cache_manager.py
class CacheManager:
    def __init__(self):
        self.max_cache_size = 1000  # 限制缓存条目数
        self.cache_ttl = 3600  # 1小时过期
```

**方案2: 定期清理Tick数据**

```python
# core/data/tick/tick_data_manager.py
async def cleanup_old_ticks(self, retain_hours: int = 24):
    """清理超过指定时间的Tick数据"""
    cutoff_time = time.time() - (retain_hours * 3600)
    self.tick_data = {
        symbol: ticks
        for symbol, ticks in self.tick_data.items()
        if ticks and ticks[-1].timestamp > cutoff_time
    }
```

**方案3: 使用生成器代替列表**

```python
# 不好的做法
def load_all_ticks():
    ticks = []
    for tick in tick_source:
        ticks.append(tick)
    return ticks

# 好的做法
def load_ticks_generator():
    for tick in tick_source:
        yield tick
```

### 4. 策略无信号生成

#### 症状

```
长时间没有交易信号
策略日志显示"无符合条件的信号"
```

#### 诊断步骤

```bash
# 1. 检查市场数据接收
tail -20 logs/websocket.log | grep "Ticker"

# 2. 检查策略配置
python scripts/validate_config.py --config configs/live_config.yaml

# 3. 运行诊断脚本
python scripts/diagnose_no_signals.py
```

#### 解决方案

**方案1: 调整策略参数**

```yaml
# configs/live_config.yaml
strategy:
  tick_breakout:
    volume_threshold: 2.0  # 降低成交量阈值
    breakout_threshold: 0.00005  # 降低突破阈值
```

**方案2: 检查数据质量**

```python
# 验证数据完整性
from core.data.data_validator import DataValidator

validator = DataValidator()
is_valid = validator.validate_tick_data(tick_data)
if not is_valid:
    print("数据验证失败:", validator.errors)
```

**方案3: 切换策略**

```bash
# 尝试其他策略
python -m core.live.high_frequency_trader \
    --config configs/traditional_grid_config.yaml \
    --mode paper
```

### 5. 数据库/文件损坏

#### 症状

```
ERROR: 无法读取Parquet文件
ERROR: 数据文件损坏
```

#### 诊断步骤

```bash
# 1. 检查文件完整性
python scripts/inspect_parquet.py --file data/tick/BTCUSDT.parquet

# 2. 检查磁盘错误
sudo fsck /dev/sda1

# 3. 查看系统日志
dmesg | grep -i error
```

#### 解决方案

**方案1: 从备份恢复**

```bash
# 恢复最近的备份
cp data/backups/tick_data_backup_$(date +%Y%m%d).tar.gz data/
tar -xzf data/tick_data_backup_*.tar.gz
```

**方案2: 重新下载数据**

```python
from core.data.data_downloader import DataDownloader

downloader = DataDownloader()
downloader.download_symbol_data("BTC/USDT", "1s", days=7)
```

**方案3: 修复Parquet文件**

```python
import pandas as pd

try:
    # 尝试读取损坏的文件
    df = pd.read_parquet("corrupted_file.parquet")
except Exception as e:
    print(f"文件损坏: {e}")
    # 使用备份或重新下载
```

---

## 应急处理

### 紧急停止交易

```bash
# 方法1: 停止systemd服务
sudo systemctl stop procrypto-trader

# 方法2: 发送TERM信号
kill -TERM $(pidof -s python)

# 方法3: 强制杀死进程 (紧急情况)
kill -9 $(pidof -s python)
```

### 紧急平仓

```python
# scripts/emergency_close_all.py
from core.trading.position_manager import PositionManager
from core.exchange.binance_api import BinanceAPI

def emergency_close_all():
    """紧急平仓所有持仓"""
    api = BinanceAPI(...)
    pm = PositionManager(api)

    positions = pm.get_all_positions()

    for position in positions:
        try:
            # 创建平仓订单
            order = pm.create_close_order(position)
            result = api.place_order(order)
            print(f"✅ 平仓成功: {position.symbol}")
        except Exception as e:
            print(f"❌ 平仓失败: {position.symbol}, 错误: {e}")

if __name__ == "__main__":
    emergency_close_all()
```

### 数据恢复流程

```bash
# 1. 停止服务
sudo systemctl stop procrypto-trader

# 2. 备份当前数据 (即使可能损坏)
cp -r data/ data/corrupted_backup/

# 3. 从最近的有效备份恢复
tar -xzf backups/data_backup_20250120.tar.gz

# 4. 验证数据完整性
python scripts/validate_data_integrity.py

# 5. 重启服务
sudo systemctl start procrypto-trader
```

### 灾难恢复

#### 完整系统恢复

```bash
#!/bin/bash
# scripts/disaster_recovery.sh

echo "开始灾难恢复流程..."

# 1. 系统检查
echo "检查系统资源..."
free -h
df -h

# 2. 恢复代码
echo "恢复代码库..."
git checkout main
git pull origin main

# 3. 恢复配置
echo "恢复配置文件..."
tar -xzf backups/configs_backup.tar.gz

# 4. 恢复数据
echo "恢复交易数据..."
tar -xzf backups/data_backup_latest.tar.gz

# 5. 重新安装依赖
echo "重新安装依赖..."
pip install -r requirements.txt

# 6. 运行测试
echo "运行系统测试..."
pytest tests/ -v

# 7. 启动服务
echo "启动服务..."
sudo systemctl start procrypto-trader

echo "灾难恢复完成！"
sudo systemctl status procrypto-trader
```

---

## 回滚流程

### 版本回滚

```bash
# 1. 查看提交历史
git log --oneline -10

# 2. 回滚到指定版本
git checkout <previous_commit_hash>

# 3. 重新安装依赖 (如有变化)
pip install -r requirements.txt

# 4. 重启服务
sudo systemctl restart procrypto-trader

# 5. 验证功能
pytest tests/
```

### 配置回滚

```bash
# 1. 备份当前配置
cp configs/live_config.yaml configs/live_config.yaml.backup

# 2. 恢复之前的配置
cp configs/archive/live_config_20250120.yaml configs/live_config.yaml

# 3. 验证配置
python scripts/validate_config.py

# 4. 重启服务
sudo systemctl restart procrypto-trader
```

### 数据库回滚 (SQLite)

```bash
# 1. 停止服务
sudo systemctl stop procrypto-trader

# 2. 备份当前数据库
cp records/trades.db records/trades.db.backup

# 3. 恢复之前的数据库
cp backups/trades_20250120.db records/trades.db

# 4. 验证数据库
python -c "
import sqlite3
conn = sqlite3.connect('records/trades.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM trades')
print(f'交易记录数: {cursor.fetchone()[0]}')
conn.close()
"

# 5. 启动服务
sudo systemctl start procrypto-trader
```

---

## 性能优化建议

### 1. 数据访问优化

```python
# 使用缓存减少重复计算
from core.cache.cache_manager import CacheManager

cache = CacheManager()

@cache.cached(ttl=3600)
def calculate_indicators(symbol):
    # 指标计算结果缓存1小时
    pass
```

### 2. WebSocket优化

```yaml
# configs/live_config.yaml
websocket:
  # 只订阅需要的交易对
  subscribe_symbols:
    - "BTCUSDT"
    - "ETHUSDT"

  # 启用压缩
  enable_compression: true

  # 调整心跳间隔
  ping_interval: 30
  ping_timeout: 10
```

### 3. 日志优化

```python
# 使用异步日志
import logging
from logging.handlers import QueueHandler
import queue

# 创建日志队列
log_queue = queue.Queue(maxsize=1000)
queue_handler = QueueHandler(log_queue)

# 使用更高效的日志级别
logging.getLogger().setLevel(logging.WARNING)  # 减少日志量
```

---

## 安全建议

### 1. API密钥管理

```bash
# 使用环境变量存储敏感信息
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"

# 或使用密钥管理工具
pip install keyring
keyring set procrypto binance_api_key
```

### 2. 访问控制

```bash
# 限制配置文件权限
chmod 600 configs/live_config.yaml
chmod 600 .env

# 使用专用运行账户
sudo useradd -r -s /bin/bash trader
sudo chown -R trader:trader /path/to/ProCryptoTrader
```

### 3. 网络安全

```bash
# 配置防火墙
sudo ufw allow 443/tcp  # 允许HTTPS
sudo ufw deny 80/tcp    # 禁止HTTP
sudo ufw enable

# 使用SSH密钥认证
ssh-keygen -t ed25519
```

---

## 联系支持

- 📧 **技术支持**: support@procrypto.trader
- 🐛 **Bug报告**: https://github.com/your-org/ProCryptoTrader/issues
- 📖 **文档**: https://docs.procrypto.trader
- 💬 **社区讨论**: https://discord.gg/procrypto

---

**最后更新**: 2025-01-28
