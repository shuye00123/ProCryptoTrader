# 策略模块架构文档

## 📋 概述

策略模块是ProCryptoTrader量化交易系统的核心决策引擎，严格遵循RIPER-5原则设计，提供了完整的策略开发框架和多种内置交易策略。该模块采用基于抽象基类的策略模式，实现了标准化的信号生成、风险控制和持仓管理机制。

## 🎯 RIPER-5原则体现

### Risk First (风险优先)
- **多层风险控制**: 基类提供止损止盈机制，各策略实现具体风险逻辑
- **仓位管理**: 严格的持仓数量限制和仓位大小控制
- **信号置信度**: 每个交易信号都包含置信度评估
- **回撤控制**: 动态监控持仓盈亏，自动触发止损机制

### Integration Minimal (最小侵入)
- **策略模式**: 所有策略继承统一接口，实现可插拔的策略架构
- **标准化信号**: 统一的Signal数据结构，策略与执行系统解耦
- **配置驱动**: 通过配置文件控制策略行为，无需修改代码
- **数据抽象**: 策略不依赖具体数据源，只处理标准化的OHLCV数据

### Predictability (可预期性)
- **确定性逻辑**: 所有策略基于明确的技术指标和量化规则
- **状态管理**: 完整的策略状态跟踪和历史记录
- **信号透明**: 每个信号包含详细的元数据和生成逻辑
- **结果可重现**: 相同数据和参数产生相同的交易信号

### Expandability (可扩展性)
- **抽象基类**: BaseStrategy提供完整的策略开发框架
- **模块化设计**: 技术指标计算、信号生成、风险控制分离
- **工厂模式**: 支持动态策略创建和注册
- **插件架构**: 新策略可无缝集成到现有系统

### Realistic Evaluation (真实可评估)
- **历史回测**: 完整的回测框架支持策略验证
- **性能指标**: 详细的策略表现统计和风险评估
- **信号统计**: 信号生成频率、成功率等量化指标
- **风险调整收益**: 夏普比率、最大回撤等风险调整后指标

## 🏗️ 模块架构

### 目录结构
```
core/strategy/
├── __init__.py                  # 模块导出
├── base_strategy.py            # 策略抽象基类
├── grid_strategy.py            # 网格策略
├── martingale_strategy.py      # 马丁格尔策略
├── dual_ma_strategy.py         # 双均线策略
├── enhanced_base_strategy.py   # 增强基类
└── enhanced_grid_strategy.py   # 增强网格策略
```

### 类层次结构
```
BaseStrategy (抽象基类)
├── SignalType (信号类型枚举)
├── Signal (交易信号类)
├── Position (持仓信息类)
└── 策略实现类
    ├── GridStrategy (网格策略)
    ├── MartingaleStrategy (马丁格尔策略)
    ├── DualMovingAverageStrategy (双均线策略)
    ├── EnhancedBaseStrategy (增强基类)
    └── EnhancedGridStrategy (增强网格策略)
```

## 📊 核心组件详解

### 1. 基础架构组件

#### SignalType 枚举
**职责**: 标准化交易信号类型定义

**信号类型**:
```python
class SignalType(Enum):
    OPEN_LONG = "open_long"          # 开多仓
    OPEN_SHORT = "open_short"        # 开空仓
    CLOSE_LONG = "close_long"        # 平多仓
    CLOSE_SHORT = "close_short"      # 平空仓
    INCREASE_LONG = "increase_long"  # 加多仓
    INCREASE_SHORT = "increase_short" # 加空仓
    HOLD = "hold"                    # 持仓不动
    CLOSE = "close"                  # 平仓（通用）
```

#### Signal 类
**职责**: 统一的交易信号数据结构

**核心属性**:
```python
class Signal:
    def __init__(self, signal_type: SignalType, symbol: str,
                 price: float = None, amount: float = None,
                 confidence: float = 1.0, stop_loss: float = None,
                 take_profit: float = None, metadata: Dict = None):

        self.signal_type = signal_type          # 信号类型
        self.symbol = symbol                    # 交易对
        self.price = price                      # 建议价格
        self.amount = amount                    # 交易数量
        self.confidence = confidence            # 信号置信度 [0,1]
        self.stop_loss = stop_loss              # 止损价格
        self.take_profit = take_profit          # 止盈价格
        self.metadata = metadata or {}          # 策略元数据
        self.timestamp = pd.Timestamp.now()     # 信号时间戳
```

**使用示例**:
```python
# 创建买入信号
buy_signal = Signal(
    signal_type=SignalType.OPEN_LONG,
    symbol="BTC/USDT",
    price=50000.0,
    amount=0.1,
    confidence=0.8,
    stop_loss=48000.0,
    take_profit=52000.0,
    metadata={'strategy': 'grid', 'level': 5}
)
```

#### Position 类
**职责**: 持仓信息管理和盈亏计算

**核心功能**:
```python
class Position:
    def __init__(self, symbol: str, side: str, amount: float,
                 entry_price: float, current_price: float = None):

        self.symbol = symbol                    # 交易对
        self.side = side                        # 持仓方向 ('long'/'short')
        self.amount = amount                    # 持仓数量
        self.entry_price = entry_price          # 开仓价格
        self.current_price = current_price or entry_price  # 当前价格
        self.unrealized_pnl = self._calculate_unrealized_pnl()
        self.unrealized_pnl_pct = self._calculate_unrealized_pnl_pct()
```

**盈亏计算**:
```python
def _calculate_unrealized_pnl(self) -> float:
    """计算未实现盈亏"""
    if self.side == 'long':
        return (self.current_price - self.entry_price) * self.amount
    else:  # short
        return (self.entry_price - self.current_price) * self.amount

def update_price(self, new_price: float):
    """更新当前价格并重新计算盈亏"""
    self.current_price = new_price
    self.unrealized_pnl = self._calculate_unrealized_pnl()
    self.unrealized_pnl_pct = self._calculate_unrealized_pnl_pct()
```

#### BaseStrategy 抽象基类
**职责**: 策略开发的统一框架和基础功能

**核心接口**:
```python
class BaseStrategy(ABC):
    def __init__(self, config: Dict):
        # 基础配置
        self.config = config
        self.name = config.get('name', self.__class__.__name__)
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '1h')

        # 持仓管理
        self.positions = {}  # {symbol: Position}
        self.signals_history = []

        # 风险控制参数
        self.max_positions = config.get('max_positions', 1)
        self.position_size = config.get('position_size', 0.1)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)
        self.take_profit_pct = config.get('take_profit_pct', 0.1)

        # 状态变量
        self.current_data = {}      # {symbol: DataFrame}
        self.indicators = {}        # {symbol: {indicator_name: value}}

    @abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """生成交易信号"""
        pass

    @abstractmethod
    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """计算技术指标"""
        pass
```

**持仓管理方法**:
```python
def add_position(self, symbol: str, side: str, amount: float, entry_price: float):
    """添加持仓"""
    self.positions[symbol] = Position(symbol, side, amount, entry_price)

def remove_position(self, symbol: str):
    """移除持仓"""
    if symbol in self.positions:
        del self.positions[symbol]

def can_open_position(self, symbol: str) -> bool:
    """检查是否可以开新仓"""
    if self.has_position(symbol):
        return False
    if len(self.positions) >= self.max_positions:
        return False
    return True

def should_stop_loss(self, symbol: str) -> bool:
    """检查是否应该止损"""
    position = self.get_position(symbol)
    if not position:
        return False
    return position.unrealized_pnl_pct <= -self.stop_loss_pct * 100

def should_take_profit(self, symbol: str) -> bool:
    """检查是否应该止盈"""
    position = self.get_position(symbol)
    if not position:
        return False
    return position.unrealized_pnl_pct >= self.take_profit_pct * 100
```

### 2. 网格策略 (GridStrategy)

#### 策略原理
网格策略在价格区间内设置多个网格线，当价格触及网格线时执行买卖操作，通过频繁的小额交易获取利润。

#### 核心参数
```python
def __init__(self, config: Dict):
    super().__init__(config)

    # 网格参数
    self.grid_count = config.get('grid_count', 10)           # 网格数量
    self.grid_range_pct = config.get('grid_range_pct', 0.1)  # 网格范围百分比
    self.base_price = None                                   # 基准价格

    # 网格状态
    self.grid_prices = {}        # {symbol: [grid_prices]}
    self.grid_levels = {}        # {symbol: {price: level}}
    self.last_price = {}         # {symbol: price}
    self.grid_orders = {}        # {symbol: {price: order_type}}
    self.executed_levels = {}    # {symbol: set(levels)}
    self.trade_history = {}      # {symbol: [trades]}
```

#### 网格初始化
```python
def _initialize_grid(self, symbol: str, base_price: float):
    """初始化网格"""
    # 计算网格价格范围
    grid_range = base_price * self.grid_range_pct
    upper_price = base_price + grid_range
    lower_price = base_price - grid_range

    # 计算网格价格
    grid_prices = np.linspace(lower_price, upper_price, self.grid_count + 1)

    # 存储网格价格和级别
    self.grid_prices[symbol] = grid_prices.tolist()
    self.grid_levels[symbol] = {price: i for i, price in enumerate(grid_prices)}

    # 初始化网格订单状态
    self.grid_orders[symbol] = {}
    for price in grid_prices:
        # 基准价格以下设置买单，以上设置卖单
        if price < base_price:
            self.grid_orders[symbol][price] = 'buy'
        elif price > base_price:
            self.grid_orders[symbol][price] = 'sell'
```

#### 网格触发逻辑
```python
def _check_grid_triggers(self, symbol: str, current_price: float) -> List[Signal]:
    """检查网格触发条件"""
    signals = []
    grid_prices = self.grid_prices[symbol]

    # 遍历网格区间
    for i in range(len(grid_prices) - 1):
        lower_grid = grid_prices[i]
        upper_grid = grid_prices[i + 1]

        # 从下往上穿过下网格线 → 买入
        if (self.last_price.get(symbol, 0) <= lower_grid and current_price > lower_grid):
            if i not in self.executed_levels[symbol]:
                signals.append(self._create_buy_signal(symbol, lower_grid))
                self.executed_levels[symbol].add(i)

                # 更新网格状态：买入后该级别变为卖出级别
                self.grid_orders[symbol][lower_grid] = 'sell'
                if i + 1 < len(grid_prices):
                    self.grid_orders[symbol][upper_grid] = 'buy'

        # 从上往下穿过上网格线 → 卖出
        elif (self.last_price.get(symbol, 0) >= upper_grid and current_price < upper_grid):
            if i + 1 not in self.executed_levels[symbol]:
                signals.append(self._create_sell_signal(symbol, upper_grid))
                self.executed_levels[symbol].add(i + 1)

                # 更新网格状态：卖出后该级别变为买入级别
                self.grid_orders[symbol][upper_grid] = 'buy'
                if i < len(grid_prices):
                    self.grid_orders[symbol][lower_grid] = 'sell'

    return signals
```

#### 技术指标计算
```python
def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
    """计算技术指标"""
    indicators = {}

    for symbol, df in data.items():
        if df.empty:
            continue

        symbol_indicators = {}
        latest_price = df['close'].iloc[-1]

        # 移动平均线
        if len(df) >= 20:
            symbol_indicators['sma_20'] = df['close'].rolling(20).mean().iloc[-1]
        if len(df) >= 50:
            symbol_indicators['sma_50'] = df['close'].rolling(50).mean().iloc[-1]

        # 波动率
        if len(df) >= 20:
            symbol_indicators['volatility_20'] = df['close'].pct_change().rolling(20).std().iloc[-1]

        # 价格区间
        if len(df) >= 20:
            symbol_indicators['high_20'] = df['high'].rolling(20).max().iloc[-1]
            symbol_indicators['low_20'] = df['low'].rolling(20).min().iloc[-1]

        # RSI
        if len(df) >= 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))

        # 初始化网格
        if self.base_price is None or symbol not in self.last_price:
            self.base_price = latest_price
            self._initialize_grid(symbol, latest_price)

        self.last_price[symbol] = latest_price
        indicators[symbol] = symbol_indicators

    return indicators
```

#### 网格状态监控
```python
def get_grid_status(self, symbol: str) -> Dict:
    """获取网格状态"""
    if symbol not in self.grid_prices:
        return {}

    return {
        'symbol': symbol,
        'base_price': self.base_price,
        'grid_count': self.grid_count,
        'grid_range_pct': self.grid_range_pct,
        'grid_prices': self.grid_prices[symbol],
        'executed_levels': list(self.executed_levels[symbol]),
        'last_price': self.last_price.get(symbol, 0),
        'trade_count': len(self.trade_history.get(symbol, [])),
        'grid_orders': self.grid_orders.get(symbol, {})
    }
```

### 3. 马丁格尔策略 (MartingaleStrategy)

#### 策略原理
马丁格尔策略在亏损时加倍下注，通过增加仓位来降低平均成本，期望最终价格回归时实现盈利。这是高风险策略，需要严格的风险控制。

#### 核心参数
```python
def __init__(self, config: Dict):
    super().__init__(config)

    # 马丁格尔参数
    self.multiplier = config.get('multiplier', 2.0)               # 加倍倍数
    self.max_levels = config.get('max_levels', 5)                 # 最大加仓级别
    self.base_position_size = config.get('base_position_size', 0.01)  # 基础仓位
    self.profit_target_pct = config.get('profit_target_pct', 0.02)    # 盈利目标

    # 持仓管理
    self.entry_price = {}                # {symbol: price}
    self.position_levels = {}            # {symbol: level}
    self.total_position_size = {}        # {symbol: size}
    self.average_entry_price = {}        # {symbol: price}
    self.trade_history = {}              # {symbol: [trades]}

    # 技术指标参数
    self.rsi_overbought = config.get('rsi_overbought', 70)   # RSI超买阈值
    self.rsi_oversold = config.get('rsi_oversold', 30)       # RSI超卖阈值
    self.trend_period = config.get('trend_period', 20)       # 趋势判断周期
```

#### 入场条件检查
```python
def _check_entry_conditions(self, symbol: str, price: float, indicators: Dict) -> Optional[Signal]:
    """检查入场条件"""
    # 技术指标分析
    trend_up = indicators.get('price_above_sma', False)      # 趋势向上
    rsi_oversold = indicators.get('rsi_oversold', False)     # RSI超卖
    price_below_bb_lower = indicators.get('price_below_bb_lower', False)  # 低于布林带下轨
    macd_bullish = indicators.get('macd_bullish', False)     # MACD金叉

    # 综合判断入场条件
    if (rsi_oversold or price_below_bb_lower) and macd_bullish:
        direction = 'long' if trend_up else 'short'

        # 记录持仓信息
        self.entry_price[symbol] = price
        self.position_levels[symbol] = 1
        self.total_position_size[symbol] = self.base_position_size
        self.average_entry_price[symbol] = price

        return Signal(
            signal_type=SignalType.OPEN_LONG if direction == 'long' else SignalType.OPEN_SHORT,
            symbol=symbol,
            price=price,
            amount=self.base_position_size,
            confidence=0.7,
            metadata={
                'strategy': 'martingale',
                'level': 1,
                'reason': 'initial_entry',
                'rsi': indicators.get('rsi'),
                'price_above_sma': trend_up
            }
        )

    return None
```

#### 加仓逻辑
```python
def _should_add_position(self, symbol: str, price: float, position) -> bool:
    """检查是否应该加仓"""
    # 检查是否达到最大级别
    if self.position_levels.get(symbol, 1) >= self.max_levels:
        return False

    # 检查是否亏损
    if position.unrealized_pnl_pct >= 0:
        return False

    # 检查亏损是否达到加仓阈值
    loss_threshold = -0.02 * self.position_levels.get(symbol, 1)  # 随级别提高降低阈值
    return position.unrealized_pnl_pct <= loss_threshold * 100

def _create_add_position_signal(self, symbol: str, price: float, position) -> Signal:
    """创建加仓信号"""
    # 计算新的仓位大小 (指数增长)
    current_level = self.position_levels.get(symbol, 1)
    new_position_size = self.base_position_size * (self.multiplier ** current_level)

    # 更新持仓信息
    self.position_levels[symbol] = current_level + 1
    self.total_position_size[symbol] += new_position_size

    # 计算新的平均入场价格
    total_cost = (self.average_entry_price[symbol] *
                 (self.total_position_size[symbol] - new_position_size) +
                 price * new_position_size)
    self.average_entry_price[symbol] = total_cost / self.total_position_size[symbol]

    return Signal(
        signal_type=SignalType.INCREASE_LONG if position.side == 'long' else SignalType.INCREASE_SHORT,
        symbol=symbol,
        price=price,
        amount=new_position_size,
        confidence=0.6,
        metadata={
            'strategy': 'martingale',
            'level': self.position_levels[symbol],
            'reason': 'add_position',
            'unrealized_pnl_pct': position.unrealized_pnl_pct
        }
    )
```

#### 技术指标计算
```python
def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
    """计算技术指标"""
    indicators = {}

    for symbol, df in data.items():
        if df.empty:
            continue

        symbol_indicators = {}

        # 趋势指标
        if len(df) >= self.trend_period:
            sma = df['close'].rolling(self.trend_period).mean()
            symbol_indicators['sma'] = sma.iloc[-1]
            symbol_indicators['price_above_sma'] = df['close'].iloc[-1] > sma.iloc[-1]

        # RSI指标
        if len(df) >= 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))
            symbol_indicators['rsi_overbought'] = symbol_indicators['rsi'] > self.rsi_overbought
            symbol_indicators['rsi_oversold'] = symbol_indicators['rsi'] < self.rsi_oversold

        # 布林带
        if len(df) >= 20:
            sma = df['close'].rolling(20).mean()
            std = df['close'].rolling(20).std()
            symbol_indicators['bb_upper'] = (sma + 2 * std).iloc[-1]
            symbol_indicators['bb_lower'] = (sma - 2 * std).iloc[-1]
            symbol_indicators['bb_middle'] = sma.iloc[-1]
            symbol_indicators['price_above_bb_upper'] = df['close'].iloc[-1] > symbol_indicators['bb_upper']
            symbol_indicators['price_below_bb_lower'] = df['close'].iloc[-1] < symbol_indicators['bb_lower']

        # MACD
        if len(df) >= 26:
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9).mean()
            symbol_indicators['macd'] = macd.iloc[-1]
            symbol_indicators['signal'] = signal.iloc[-1]
            symbol_indicators['macd_histogram'] = symbol_indicators['macd'] - symbol_indicators['signal']
            symbol_indicators['macd_bullish'] = symbol_indicators['macd'] > symbol_indicators['signal']

        indicators[symbol] = symbol_indicators

    return indicators
```

#### 马丁格尔状态监控
```python
def get_martingale_status(self, symbol: str) -> Dict:
    """获取马丁格尔策略状态"""
    return {
        'symbol': symbol,
        'multiplier': self.multiplier,
        'max_levels': self.max_levels,
        'base_position_size': self.base_position_size,
        'profit_target_pct': self.profit_target_pct,
        'current_level': self.position_levels.get(symbol, 0),
        'total_position_size': self.total_position_size.get(symbol, 0),
        'average_entry_price': self.average_entry_price.get(symbol, 0),
        'entry_price': self.entry_price.get(symbol, 0),
        'trade_count': len(self.trade_history.get(symbol, [])),
        'has_position': self.has_position(symbol)
    }
```

### 4. 双均线策略 (DualMovingAverageStrategy)

#### 策略原理
双均线策略使用短期和长期移动平均线的交叉来产生交易信号。金叉（短期均线上穿长期均线）产生买入信号，死叉（短期均线下穿长期均线）产生卖出信号。

#### 核心参数
```python
def __init__(self, config: Dict):
    super().__init__(config)

    # 均线参数
    self.short_period = config.get('short_period', 10)  # 短期均线周期
    self.long_period = config.get('long_period', 20)    # 长期均线周期

    # 参数验证
    if self.short_period >= self.long_period:
        raise ValueError("短期均线周期必须小于长期均线周期")

    # 交易参数
    self.position_size = config.get('position_size', 0.5)
    self.stop_loss_pct = config.get('stop_loss_pct', 0.05)
    self.take_profit_pct = config.get('take_profit_pct', 0.1)

    # 状态变量
    self.short_ma = {}          # {symbol: value}
    self.long_ma = {}           # {symbol: value}
    self.prev_short_ma = {}     # {symbol: value}
    self.prev_long_ma = {}      # {symbol: value}
    self.position_opened = {}   # {symbol: bool}
    self.entry_price = {}       # {symbol: price}
```

#### 均线交叉检测
```python
def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
    """计算技术指标"""
    indicators = {}

    for symbol, df in data.items():
        if df.empty or len(df) < self.long_period:
            continue

        symbol_indicators = {}

        # 保存前一期均线值
        self.prev_short_ma[symbol] = self.short_ma.get(symbol)
        self.prev_long_ma[symbol] = self.long_ma.get(symbol)

        # 计算均线
        self.short_ma[symbol] = df['close'].rolling(window=self.short_period).mean().iloc[-1]
        self.long_ma[symbol] = df['close'].rolling(window=self.long_period).mean().iloc[-1]

        # 均线状态
        symbol_indicators['short_ma'] = self.short_ma[symbol]
        symbol_indicators['long_ma'] = self.long_ma[symbol]
        symbol_indicators['short_ma_above_long'] = self.short_ma[symbol] > self.long_ma[symbol]

        # 交叉检测
        if (self.prev_short_ma.get(symbol) is not None and
            self.prev_long_ma.get(symbol) is not None):

            # 金叉：短期均线上穿长期均线
            symbol_indicators['golden_cross'] = (
                self.prev_short_ma[symbol] <= self.prev_long_ma[symbol] and
                self.short_ma[symbol] > self.long_ma[symbol]
            )

            # 死叉：短期均线下穿长期均线
            symbol_indicators['death_cross'] = (
                self.prev_short_ma[symbol] >= self.prev_long_ma[symbol] and
                self.short_ma[symbol] < self.long_ma[symbol]
            )

        # 价格与均线关系
        latest_price = df['close'].iloc[-1]
        symbol_indicators['price_above_short_ma'] = latest_price > self.short_ma[symbol]
        symbol_indicators['price_above_long_ma'] = latest_price > self.long_ma[symbol]

        # RSI过滤
        if len(df) >= 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))

        indicators[symbol] = symbol_indicators

    return indicators
```

#### 入场条件检查
```python
def _check_entry_conditions(self, symbol: str, price: float, indicators: Dict) -> Optional[Signal]:
    """检查入场条件"""
    # 金叉信号
    golden_cross = indicators.get('golden_cross', False)

    # 趋势确认
    short_above_long = indicators.get('short_ma_above_long', False)

    # RSI过滤
    rsi = indicators.get('rsi', 50)
    rsi_reasonable = 30 < rsi < 70  # 避免超买超卖区间

    # 综合判断
    if (golden_cross or short_above_long) and rsi_reasonable:
        # 记录入场信息
        self.entry_price[symbol] = price
        self.position_opened[symbol] = True

        return Signal(
            signal_type=SignalType.OPEN_LONG,
            symbol=symbol,
            price=price,
            amount=self.position_size,
            confidence=0.7,
            metadata={
                'strategy': 'dual_ma',
                'short_ma': indicators.get('short_ma'),
                'long_ma': indicators.get('long_ma'),
                'rsi': rsi,
                'reason': 'golden_cross' if golden_cross else 'short_above_long'
            }
        )

    return None
```

#### 平仓条件检查
```python
def _should_close_position(self, symbol: str, price: float, position, indicators: Dict) -> bool:
    """检查是否应该平仓"""
    # 死叉信号
    death_cross = indicators.get('death_cross', False)

    # 趋势反转
    short_below_long = not indicators.get('short_ma_above_long', False)

    # 止损止盈检查
    entry_price = self.entry_price.get(symbol, price)

    if position.is_long:
        # 多头止损
        stop_loss_price = entry_price * (1 - self.stop_loss_pct)
        stop_loss_triggered = price <= stop_loss_price

        # 多头止盈
        take_profit_price = entry_price * (1 + self.take_profit_pct)
        take_profit_triggered = price >= take_profit_price
    else:
        # 空头止损
        stop_loss_price = entry_price * (1 + self.stop_loss_pct)
        stop_loss_triggered = price >= stop_loss_price

        # 空头止盈
        take_profit_price = entry_price * (1 - self.take_profit_pct)
        take_profit_triggered = price <= take_profit_price

    # 任一条件触发即平仓
    return death_cross or short_below_long or stop_loss_triggered or take_profit_triggered
```

## 🔧 策略开发指南

### 创建自定义策略

#### 1. 继承BaseStrategy
```python
from core.strategy.base_strategy import BaseStrategy, Signal, SignalType
from typing import Dict, List
import pandas as pd
import numpy as np

class CustomStrategy(BaseStrategy):
    """自定义策略示例"""

    def __init__(self, config: Dict):
        super().__init__(config)

        # 策略特定参数
        self.custom_param = config.get('custom_param', 1.0)
        self.indicator_period = config.get('indicator_period', 20)

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """计算技术指标"""
        indicators = {}

        for symbol, df in data.items():
            if df.empty:
                continue

            symbol_indicators = {}

            # 自定义技术指标
            if len(df) >= self.indicator_period:
                # 示例：自定义均线
                symbol_indicators['custom_ma'] = df['close'].rolling(self.indicator_period).mean().iloc[-1]

                # 示例：自定义振荡器
                symbol_indicators['custom_oscillator'] = (
                    (df['close'] - df['low'].rolling(14).min()) /
                    (df['high'].rolling(14).max() - df['low'].rolling(14).min())
                ).iloc[-1]

            indicators[symbol] = symbol_indicators

        return indicators

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """生成交易信号"""
        signals = []

        for symbol, df in data.items():
            if df.empty:
                continue

            latest_price = df['close'].iloc[-1]
            indicators = self.indicators.get(symbol, {})

            # 自定义信号生成逻辑
            if not self.has_position(symbol):
                # 检查入场条件
                entry_signal = self._check_custom_entry(symbol, latest_price, indicators)
                if entry_signal:
                    signals.append(entry_signal)
            else:
                # 检查平仓条件
                position = self.get_position(symbol)
                if self._should_custom_close(symbol, latest_price, position, indicators):
                    close_signal = self._create_custom_close_signal(symbol, latest_price, position)
                    signals.append(close_signal)

        return signals

    def _check_custom_entry(self, symbol: str, price: float, indicators: Dict) -> Optional[Signal]:
        """自定义入场条件检查"""
        # 实现自定义入场逻辑
        custom_condition = indicators.get('custom_oscillator', 0.5) > 0.8

        if custom_condition and self.can_open_position(symbol):
            return Signal(
                signal_type=SignalType.OPEN_LONG,
                symbol=symbol,
                price=price,
                amount=self.position_size,
                confidence=0.7,
                metadata={'strategy': 'custom', 'reason': 'custom_entry'}
            )

        return None

    def _should_custom_close(self, symbol: str, price: float, position, indicators: Dict) -> bool:
        """自定义平仓条件检查"""
        # 实现自定义平仓逻辑
        return (self.should_stop_loss(symbol) or
                self.should_take_profit(symbol) or
                indicators.get('custom_oscillator', 0.5) < 0.2)

    def _create_custom_close_signal(self, symbol: str, price: float, position) -> Signal:
        """创建自定义平仓信号"""
        signal_type = SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=position.amount,
            confidence=0.9,
            metadata={'strategy': 'custom', 'reason': 'custom_close'}
        )
```

#### 2. 策略配置
```yaml
# custom_strategy_config.yaml
strategy:
  name: "CustomStrategy"
  class: "CustomStrategy"

  # 通用参数
  symbols: ["BTC/USDT", "ETH/USDT"]
  timeframe: "1h"
  max_positions: 2
  position_size: 0.2
  stop_loss_pct: 0.05
  take_profit_pct: 0.15

  # 策略特定参数
  custom_param: 1.5
  indicator_period: 25
```

#### 3. 策略使用
```python
from core.strategy.custom_strategy import CustomStrategy

# 加载配置
import yaml
with open('custom_strategy_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# 创建策略实例
strategy = CustomStrategy(config['strategy'])

# 使用策略
data = {'BTC/USDT': ohlcv_data}
signals = strategy.update(data)

# 获取策略状态
status = strategy.get_status()
print(f"策略状态: {status}")
```

## 📈 策略性能评估

### 关键指标
```python
def calculate_strategy_performance(signals_history: List[Signal],
                                  positions_history: Dict) -> Dict:
    """计算策略性能指标"""

    # 基础统计
    total_signals = len(signals_history)
    profitable_trades = sum(1 for pos in positions_history.values()
                           if pos.unrealized_pnl > 0)

    # 收益指标
    total_pnl = sum(pos.unrealized_pnl for pos in positions_history.values())
    total_return = total_pnl / initial_balance if initial_balance > 0 else 0

    # 风险指标
    max_drawdown = calculate_max_drawdown(positions_history)
    win_rate = profitable_trades / len(positions_history) if positions_history else 0

    return {
        'total_signals': total_signals,
        'total_trades': len(positions_history),
        'profitable_trades': profitable_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': calculate_sharpe_ratio(total_return, max_drawdown)
    }
```

## 🛡️ 风险控制机制

### 1. 多层风险控制
- **策略级风险**: 每个策略内部的止损止盈逻辑
- **系统级风险**: BaseStrategy提供的最大持仓数量限制
- **信号级风险**: Signal对象包含置信度评估
- **执行级风险**: 外部风险管理系统验证

### 2. 仓位管理
- **固定比例**: 基于总资金的固定比例开仓
- **动态调整**: 根据波动率和风险水平动态调整仓位
- **分散投资**: 支持多交易对的资金分散

### 3. 止损机制
- **固定止损**: 基于开仓价格的固定百分比止损
- **移动止损**: 跟踪价格变化的移动止损
- **时间止损**: 基于持仓时间的止损机制

## 🔌 扩展功能

### 1. 策略组合
```python
class StrategyPortfolio:
    """策略组合管理"""

    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies
        self.weights = [1.0 / len(strategies)] * len(strategies)  # 等权重

    def generate_combined_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """生成组合信号"""
        all_signals = []

        for strategy, weight in zip(self.strategies, self.weights):
            signals = strategy.update(data)
            # 调整信号权重
            for signal in signals:
                signal.amount *= weight
                signal.confidence *= weight
            all_signals.extend(signals)

        return self._filter_conflicts(all_signals)

    def _filter_conflicts(self, signals: List[Signal]) -> List[Signal]:
        """过滤冲突信号"""
        # 实现信号冲突过滤逻辑
        pass
```

### 2. 动态参数调整
```python
class AdaptiveStrategy(BaseStrategy):
    """自适应策略"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.adaptive_params = {}
        self.performance_history = []

    def adaptive_parameters(self, recent_performance: Dict):
        """根据近期表现动态调整参数"""
        if recent_performance['win_rate'] < 0.4:
            # 胜率低，减少仓位大小
            self.position_size *= 0.9
        elif recent_performance['win_rate'] > 0.6:
            # 胜率高，增加仓位大小
            self.position_size *= 1.1

        # 确保仓位大小在合理范围内
        self.position_size = max(0.01, min(0.5, self.position_size))
```

## 📚 最佳实践

### 1. 策略开发
- **清晰的信号逻辑**: 每个信号都应有明确的生成逻辑
- **完整的风险控制**: 实现多层次的风险管理机制
- **参数化设计**: 策略参数应可配置和调整
- **充分的测试**: 在多种市场环境下测试策略表现

### 2. 性能优化
- **避免重复计算**: 缓存计算结果提高效率
- **向量化操作**: 使用pandas/numpy向量化计算
- **内存管理**: 及时清理不需要的数据
- **并发处理**: 在可能的情况下实现并发计算

### 3. 风险管理
- **仓位控制**: 严格控制单笔交易和总仓位大小
- **止损执行**: 确保止损机制的有效执行
- **分散投资**: 在多个交易对之间分散风险
- **定期评估**: 定期评估策略表现和风险水平

---

本策略模块文档提供了完整的策略开发框架和使用指南，严格遵循RIPER-5原则，为量化交易系统提供了可靠、高效、可扩展的策略决策能力。所有策略实现都基于实际获取的价格数据，不使用任何模拟或假设性数据。