# 🔧 ReconnectingWebsocket 异步迭代错误修复

## ❌ 错误信息

```python
'async for' requires an object with __aiter__ method, got ReconnectingWebsocket
```

## 🔍 根本原因

### 错误代码

```python
async def _process_timeframe_stream(self, timeframe: str, socket):
    async for msg in socket:  # ❌ 错误：ReconnectingWebsocket 不支持 async for
        if not self.ws_running:
            break
        # 处理消息
```

**问题**：
- `ReconnectingWebsocket` 对象**不是异步迭代器**
- 没有 `__aiter__()` 方法
- `async for` 无法直接迭代 `ReconnectingWebsocket` 对象

### python-binance 官方推荐方式

根据 [python-binance 官方文档](https://python-binance.readthedocs.io/en/latest/websockets.html)：

```python
import asyncio
from binance import AsyncClient, BinanceSocketManager

async def main():
    client = await AsyncClient.create()
    bm = BinanceSocketManager(client)

    # 创建 socket
    ts = bm.trade_socket('BNBBTC')

    # 使用上下文管理器接收消息（官方推荐）
    async with ts as tscm:
        while True:
            res = await tscm.recv()  # ← 使用 recv() 方法
            print(res)

    await client.close_connection()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```

**关键点**：
1. ✅ 使用 `async with socket as tscm:` 进入上下文管理器
2. ✅ 使用 `await tscm.recv()` 接收消息（不是 async for）
3. ✅ 使用 `while True` 循环持续接收
4. ✅ 检查 `msg is None` 判断连接是否关闭

## 🔧 修复方案

### 修改前（错误代码）

**位置1**: `_start_timeframe_subscription` 第218行

```python
socket = self.bsm.multiplex_socket(streams)
await socket.__aenter__()  # ❌ 手动调用 __aenter__
self.sockets[timeframe] = socket
```

**位置2**: `_process_timeframe_stream` 第253行

```python
try:
    async for msg in socket:  # ❌ 错误：不支持 async for
        if not self.ws_running:
            break
        # 处理消息
```

### 修改后（正确代码）

**位置1**: `_start_timeframe_subscription` 第217-219行

```python
# 创建multiplex socket
socket = self.bsm.multiplex_socket(streams)
# 注意：不在这里调用 __aenter__()，而是在 _process_timeframe_stream 中使用 async with
self.sockets[timeframe] = socket
```

**位置2**: `_process_timeframe_stream` 第234-285行

```python
async def _process_timeframe_stream(self, timeframe: str, socket):
    """
    处理特定时间框架的K线数据流

    根据python-binance官方文档，使用async with + recv()方式接收消息
    参考: https://python-binance.readthedocs.io/en/latest/websockets.html
    """
    handler = self.handlers.get(timeframe)

    if not handler:
        logger.error(f"[MultiTimeframeSubscriber] {timeframe}没有注册处理器")
        return

    logger.info(f"[MultiTimeframeSubscriber] {timeframe}数据流处理任务已启动")

    try:
        # 使用上下文管理器接收消息（官方推荐方式）
        async with socket as tscm:
            while self.ws_running:
                try:
                    # 使用 recv() 方法接收消息
                    msg = await tscm.recv()

                    if msg is None:
                        logger.debug(f"[MultiTimeframeSubscriber] {timeframe}接收到空消息，停止")
                        break

                    # 更新统计
                    if self.enable_stats:
                        self.stats[timeframe]['messages_received'] += 1
                        self.stats[timeframe]['last_message_time'] = datetime.now()

                    # 调用注册的处理器
                    if asyncio.iscoroutinefunction(handler):
                        await handler(msg)
                    else:
                        handler(msg)

                    # 更新处理统计
                    if self.enable_stats:
                        self.stats[timeframe]['messages_processed'] += 1

                except Exception as e:
                    logger.error(f"[MultiTimeframeSubscriber] {timeframe}消息处理错误: {e}")
                    if self.enable_stats:
                        self.stats[timeframe]['errors'] += 1

    except asyncio.CancelledError:
        logger.info(f"[MultiTimeframeSubscriber] {timeframe}处理任务被取消")
    except Exception as e:
        logger.error(f"[MultiTimeframeSubscriber] {timeframe}数据流错误: {e}")
        # 尝试重连
        if self.ws_running:
            await self._handle_reconnect(timeframe)
```

## 📊 关键修改对比

| 方面 | 修改前 | 修改后 |
|------|--------|--------|
| 上下文管理 | 手动调用 `__aenter__()` | 使用 `async with socket as tscm:` |
| 消息接收 | `async for msg in socket` | `while ws_running: msg = await tscm.recv()` |
| 空消息处理 | 无 | 检查 `msg is None` 并 break |
| 官方兼容性 | ❌ 不兼容 | ✅ 完全兼容 |
| 代码行数 | 27行 | 33行 |

## 🧪 测试验证

### 测试命令

```bash
python main.py live --config configs/mt_kline_breakout_config.yaml
```

### 预期结果（修复前）

```
❌ ERROR: 'async for' requires an object with __aiter__ method, got ReconnectingWebsocket
❌ WARNING: 1h连接断开，1.0秒后第1次重连...
❌ ERROR: 'async for' requires an object with __aiter__ method, got ReconnectingWebsocket
❌ WARNING: 15m连接断开，1.0秒后第1次重连...
```

### 预期结果（修复后）

```
✅ [MultiTimeframeSubscriber] 创建1s订阅流: ['btcusdt@kline_1s', 'ethusdt@kline_1s', 'bnbusdt@kline_1s']...
✅ [MultiTimeframeSubscriber] ✅ 1s订阅启动成功
✅ [MultiTimeframeSubscriber] 1s数据流处理任务已启动
✅ [MultiTimeframeSubscriber] 创建15m订阅流: ['btcusdt@kline_15m', 'ethusdt@kline_15m', 'bnbusdt@kline_15m']...
✅ [MultiTimeframeSubscriber] ✅ 15m订阅启动成功
✅ [MultiTimeframeSubscriber] 15m数据流处理任务已启动
✅ [MultiTimeframeSubscriber] 创建1h订阅流: ['btcusdt@kline_1h', 'ethusdt@kline_1h', 'bnbusdt@kline_1h']...
✅ [MultiTimeframeSubscriber] ✅ 1h订阅启动成功
✅ [MultiTimeframeSubscriber] 1h数据流处理任务已启动
✅ [MultiTimeframeSubscriber] ✅ 所有订阅启动成功: ['1s', '15m', '1h']
```

## 💡 经验教训

### 1. 遵循官方文档

**错误做法**：
- 自己猜测API使用方式
- 使用看似合理的 `async for` 语法

**正确做法**：
- ✅ 查看官方文档
- ✅ 参考官方示例代码
- ✅ 使用推荐的API模式

### 2. 异步迭代器的限制

**Python 异步迭代器要求**：
- 对象必须实现 `__aiter__()` 方法
- `__aiter__()` 必须返回异步迭代器对象
- `async for` 才能工作

**ReconnectingWebsocket 的情况**：
- ❌ 没有实现 `__aiter__()` 方法
- ✅ 提供了 `recv()` 方法接收消息
- ✅ 支持上下文管理器协议 (`__aenter__`, `__aexit__`)

### 3. 上下文管理器 vs 手动管理

**推荐方式**（使用上下文管理器）：
```python
async with socket as tscm:
    while True:
        msg = await tscm.recv()
        # 自动处理连接关闭、清理等
```

**手动方式**（不推荐，除非必要）：
```python
await socket.__aenter__()
try:
    while True:
        msg = await socket.recv()
        # 处理消息
finally:
    await socket.__aexit__(None, None, None)
```

## 📚 参考文档

- [python-binance Websockets](https://python-binance.readthedocs.io/en/latest/websockets.html)
- [Python Async Iterator](https://docs.python.org/3/reference/expressions.html#async-for)
- [Python Context Managers](https://docs.python.org/3/reference/datamodel.html#async-context-managers)

## ✅ 修复验证清单

- [x] 移除 `await socket.__aenter__()` 调用
- [x] 使用 `async with socket as tscm:` 上下文管理器
- [x] 使用 `await tscm.recv()` 接收消息
- [x] 添加 `msg is None` 空消息检查
- [x] 保持原有的统计和错误处理逻辑
- [x] 代码提交（commit e2f887d）
- [x] 创建修复文档
- [ ] 用户测试验证

## 📈 影响范围

### 修改文件
- `core/strategy/multi_timeframe_subscriber.py`: 2处修改
  - 第218行：移除 `__aenter__()` 调用
  - 第234-285行：重写消息接收逻辑

### 影响的策略
- ✅ `MultiTimeframeKlineBreakoutStrategy`: 修复后可正常使用
- ✅ 所有使用 `MultiTimeframeKlineSubscriber` 的策略

### 不影响
- ❌ `HighFrequencyBreakoutStrategy`: 使用不同的WebSocket实现
- ❌ 其他非WebSocket相关功能

## 🎯 总结

**问题**: `ReconnectingWebsocket` 不支持 `async for` 迭代

**根本原因**: python-binance 的 API 设计需要使用 `async with` + `recv()` 方式

**解决方案**:
1. 使用 `async with socket as tscm:` 上下文管理器
2. 使用 `while self.ws_running: msg = await tscm.recv()` 接收消息
3. 检查 `msg is None` 判断连接状态

**参考**: python-binance 官方文档示例代码

---

**修复完成时间**: 2025-01-28
**修复验证**: ⏳ 待用户测试
**代码提交**: ✅ e2f887d
**文档记录**: ✅ 已完成
