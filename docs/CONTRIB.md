# 贡献指南 (Contributing Guide)

欢迎为ProCryptoTrader项目做出贡献！本文档将帮助您快速了解开发流程、环境设置和测试规范。

## 目录

- [开发环境设置](#开发环境设置)
- [项目结构](#项目结构)
- [开发工作流](#开发工作流)
- [代码规范](#代码规范)
- [测试流程](#测试流程)
- [提交规范](#提交规范)
- [文档更新](#文档更新)

---

## 开发环境设置

### 系统要求

- **Python版本**: >= 3.8 (推荐 3.10+)
- **操作系统**: Windows, macOS, Linux
- **内存**: 至少 4GB RAM
- **磁盘空间**: 至少 2GB 可用空间

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://github.com/your-org/ProCryptoTrader.git
cd ProCryptoTrader
```

#### 2. 创建虚拟环境

**推荐使用Python venv模块**:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

#### 3. 安装依赖

**生产环境依赖**:
```bash
pip install -r requirements.txt
```

**开发环境依赖** (包含测试和代码质量工具):
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**使用setup.py安装** (可选):
```bash
pip install -e .

# 安装所有可选依赖
pip install -e ".[all]"
```

#### 4. 配置环境变量

复制示例配置文件并根据需要修改:

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置交易所API密钥:

```bash
# Binance API配置
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_SANDBOX=true

# OKX API配置 (可选)
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase
```

#### 5. 验证安装

```bash
python -c "import ccxt; import pandas; import numpy; print('✅ 安装成功!')"
```

---

## 项目结构

```
ProCryptoTrader/
├── core/                        # 核心业务逻辑
│   ├── analysis/               # 分析模块 (绩效分析、绘图、因子分析)
│   ├── backtest/               # 回测引擎 (Backtester, Metrics, ReportGenerator)
│   ├── cache/                  # 缓存系统 (CacheManager, MemoryBackend, RedisBackend)
│   ├── containers/             # 依赖注入容器
│   ├── data/                   # 数据管理层
│   │   ├── repositories/       # Repository模式数据访问
│   │   ├── tick/               # Tick数据管理
│   │   └── *.py                # 数据服务类
│   ├── exchange/               # 交易所接口 (BinanceAPI, OKXAPI)
│   ├── interfaces/             # 业务接口定义
│   ├── live/                   # 实盘交易模块
│   ├── models/                 # 统一数据模型 (Position, Order, Signal, Trade)
│   ├── optimization/           # 性能优化模块
│   ├── services/               # 服务层 (SignalService, ExecutionService)
│   ├── strategy/               # 策略模块
│   │   ├── base_strategy.py
│   │   ├── grid_strategy.py
│   │   ├── high_frequency_breakout.py
│   │   └── ...
│   └── utils/                  # 工具模块 (Logger, RiskManager)
├── configs/                    # 配置文件目录
│   ├── hf_breakout_live_config.yaml
│   ├── traditional_grid_backtest.yaml
│   └── ...
├── docs/                       # 文档目录
├── examples/                   # 示例代码
│   ├── backtest_example.py
│   ├── live_example.py
│   └── strategy_example.py
├── scripts/                    # 工具脚本目录
├── tests/                      # 测试代码
├── data/                       # 数据存储目录
├── logs/                       # 日志文件目录
├── records/                    # 交易记录目录
├── requirements.txt            # 生产环境依赖
├── requirements-dev.txt        # 开发环境依赖
├── setup.py                    # 安装脚本
├── CLAUDE.md                   # 项目完整文档
└── README.md                   # 项目说明
```

---

## 开发工作流

### 1. Fork和分支

```bash
# 1. Fork项目到您的GitHub账号
# 2. 克隆您的fork仓库
git clone https://github.com/your-username/ProCryptoTrader.git

# 3. 添加上游仓库
git remote add upstream https://github.com/original-org/ProCryptoTrader.git

# 4. 创建功能分支
git checkout -b feature/your-feature-name
```

### 2. 开发流程

#### 编码阶段

```bash
# 1. 进行您的代码修改
# ...

# 2. 运行代码格式化
black core/ tests/ examples/

# 3. 运行代码检查
flake8 core/ tests/ examples/

# 4. 排序导入
isort core/ tests/ examples/

# 5. 运行类型检查 (可选)
mypy core/
```

#### 测试阶段

```bash
# 1. 运行所有测试
pytest

# 2. 运行特定测试文件
pytest tests/test_data.py

# 3. 运行特定测试函数
pytest tests/test_data.py::TestDataLoader::test_load_csv

# 4. 查看测试覆盖率
pytest --cov=core --cov-report=html

# 5. 并行运行测试 (加速)
pytest -n auto
```

### 3. 提交更改

```bash
# 1. 查看修改状态
git status

# 2. 添加修改的文件
git add path/to/your/file.py

# 3. 提交更改 (遵循提交规范)
git commit -m "feat: 添加新高频突破策略"

# 4. 推送到您的fork仓库
git push origin feature/your-feature-name
```

### 4. 创建Pull Request

1. 访问您的fork仓库页面
2. 点击"Compare & pull request"按钮
3. 填写PR描述模板
4. 等待代码审查

---

## 代码规范

### Python代码风格

我们遵循 **PEP 8** 规范，并使用以下工具强制执行:

#### Black (代码格式化)

```bash
# 格式化代码
black core/ tests/ examples/

# 检查格式化差异
black --check core/ tests/ examples/
```

#### Flake8 (代码检查)

```bash
# 运行检查
flake8 core/ tests/ examples/

# 常用参数
flake8 --max-line-length=100 --ignore=E203,W503 core/
```

#### isort (导入排序)

```bash
# 排序导入
isort core/ tests/ examples/

# 检查导入排序
isort --check-only core/ tests/ examples/
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **模块名** | 小写下划线 | `data_manager.py`, `risk_tools.py` |
| **类名** | 大驼峰 | `Backtester`, `DataManager`, `RiskManager` |
| **函数/方法** | 小写下划线 | `calculate_signals()`, `load_data()` |
| **变量** | 小写下划线 | `price_data`, `order_size` |
| **常量** | 大写下划线 | `MAX_POSITION_SIZE`, `DEFAULT_TIMEFRAME` |
| **私有成员** | 前缀下划线 | `_internal_method`, `_private_var` |

### 文档字符串规范

使用 **Google风格** 文档字符串:

```python
def calculate_position_size(capital: float, risk_percentage: float, stop_loss: float) -> float:
    """计算仓位大小基于风险百分比

    Args:
        capital (float): 可用资金
        risk_percentage (float): 风险百分比 (0-1之间)
        stop_loss (float): 止损价格距离

    Returns:
        float: 计算得到的仓位大小

    Raises:
        ValueError: 如果参数不合法

    Example:
        >>> calculate_position_size(10000, 0.02, 0.05)
        4.0
    """
    if risk_percentage <= 0 or risk_percentage > 1:
        raise ValueError("风险百分比必须在0-1之间")

    return capital * risk_percentage / stop_loss
```

---

## 测试流程

### 测试结构

```
tests/
├── base.py                     # 基础测试类
├── utils.py                    # 测试工具函数
├── test_data.py                # 数据模块测试
├── test_backtest.py            # 回测模块测试
├── test_strategies.py          # 策略模块测试
├── test_trading.py             # 交易模块测试
├── test_utils.py               # 工具模块测试
└── tick_data/                  # Tick数据测试
```

### 编写测试

#### 基础测试示例

```python
import unittest
from tests.base import BaseTestCase
from core.data.data_loader import DataLoader

class TestDataLoader(BaseTestCase):
    """DataLoader单元测试"""

    def setUp(self):
        """测试前准备"""
        super().setUp()
        self.loader = DataLoader()

    def test_load_csv(self):
        """测试加载CSV数据"""
        # 创建测试数据
        test_data = self.create_test_data()

        # 执行测试
        result = self.loader.load_csv(test_data)

        # 断言
        self.assertFalse(result.empty)
        self.assert_dataframes_equal(result, test_data)

    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        with self.assertRaises(FileNotFoundError):
            self.loader.load_csv("nonexistent.csv")
```

#### 异步测试示例

```python
import pytest
import asyncio
from core.data.websocket_client import WebSocketClient

@pytest.mark.asyncio
async def test_websocket_connection():
    """测试WebSocket连接"""
    client = WebSocketClient()

    try:
        await client.connect()
        assert client.is_connected()
    finally:
        await client.disconnect()
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定目录的测试
pytest tests/test_data/

# 详细输出
pytest -v

# 显示print输出
pytest -s

# 运行带标记的测试
pytest -m "not slow"

# 并行运行测试
pytest -n auto

# 生成覆盖率报告
pytest --cov=core --cov-report=html --cov-report=term
```

### 测试覆盖率

目标: **85%** 以上的代码覆盖率

```bash
# 查看覆盖率报告
pytest --cov=core --cov-report=html

# 在浏览器中查看详细报告
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

---

## 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

### 提交消息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type类型

| Type | 说明 | 示例 |
|------|------|------|
| **feat** | 新功能 | `feat(strategy): 添加高频突破策略` |
| **fix** | Bug修复 | `fix(data): 修复数据加载内存泄漏` |
| **docs** | 文档更新 | `docs(readme): 更新安装说明` |
| **style** | 代码格式调整 | `style(core): 统一代码缩进` |
| **refactor** | 重构 | `refactor(exchange): 重构API接口` |
| **perf** | 性能优化 | `perf(cache): 优化缓存命中率` |
| **test** | 测试相关 | `test(backtest): 添加回测单元测试` |
| **chore** | 构建/工具相关 | `chore(deps): 更新依赖版本` |

### 示例提交

```bash
# 简单提交
git commit -m "fix: 修复网格策略持仓计算错误"

# 带作用域的提交
git commit -m "feat(strategy): 实现高频突破策略"

# 带详细说明的提交
git commit -m "feat(data): 添加Tick数据持久化功能

- 实现异步Tick保存器
- 支持Parquet格式存储
- 添加内存监控机制

Closes #123"
```

---

## 常用开发脚本

### 代码质量检查

```bash
# 完整的代码质量检查流程
black core/ tests/ examples/          # 格式化代码
isort core/ tests/ examples/          # 排序导入
flake8 core/ tests/ examples/         # 代码检查
mypy core/                            # 类型检查
pytest --cov=core                     # 运行测试和覆盖率
```

### 数据管理脚本

```bash
# 下载数据
python scripts/download_test_data.py

# 验证数据格式
python scripts/check_data_format.py

# 分析Tick数据
python scripts/analyze_tick_data.py
```

### 策略测试脚本

```bash
# 运行回测示例
python examples/backtest_example.py

# 运行实盘交易示例 (模拟模式)
python examples/live_example.py

# 验证策略配置
python scripts/verify_production_code.py
```

---

## 文档更新

### 文档类型

| 文档 | 路径 | 说明 |
|------|------|------|
| **项目说明** | `README.md` | 项目概览和快速开始 |
| **架构文档** | `CLAUDE.md` | 完整系统架构文档 |
| **贡献指南** | `docs/CONTRIB.md` | 本文档 |
| **运维手册** | `docs/RUNBOOK.md` | 部署和运维指南 |
| **API文档** | `docs/API.md` | API接口文档 |
| **迁移指南** | `docs/MIGRATION_GUIDE.md` | 版本迁移指南 |

### 更新文档

当您修改代码时，请同步更新相关文档:

1. **新增功能**: 更新README.md和CLAUDE.md
2. **API变更**: 更新docs/API.md
3. **架构调整**: 更新CLAUDE.md
4. **配置变更**: 更新configs/目录下的相关配置文件

---

## 常见问题

### Q: 如何调试WebSocket连接问题?

```bash
# 运行WebSocket调试脚本
python scripts/diagnose_websocket.py

# 查看WebSocket日志
tail -f logs/websocket.log
```

### Q: 如何优化回测性能?

```bash
# 使用性能分析工具
python -m cProfile -o profile.stats examples/backtest_example.py

# 查看性能报告
python -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

### Q: 如何处理依赖冲突?

```bash
# 查看依赖树
pipdeptree

# 检查安全漏洞
safety check

# 更新依赖到最新兼容版本
pip install --upgrade --upgrade-strategy eager -r requirements.txt
```

---

## 获取帮助

- 📧 **Email**: contact@procrypto.trader
- 🐛 **Bug报告**: [GitHub Issues](https://github.com/your-org/ProCryptoTrader/issues)
- 💬 **讨论**: [GitHub Discussions](https://github.com/your-org/ProCryptoTrader/discussions)
- 📖 **文档**: [完整文档](CLAUDE.md)

---

## 许可证

通过贡献代码，您同意您的贡献将按照项目的MIT许可证进行授权。

---

**感谢您的贡献！** 🎉
