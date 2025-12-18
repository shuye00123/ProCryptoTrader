"""
Webhook通知工具模块
=====================================

提供通用的webhook通知功能，支持多种通知平台和消息格式。

特性:
- 异步HTTP请求，非阻塞通知
- 支持多种webhook平台（飞书、钉钉、企业微信等）
- 消息模板和自定义格式
- 重试机制和错误处理
- 请求限流和批量发送
- 签名验证和安全机制

@Author: ProCryptoTrader Team
@Date: 2024-12-14
"""

import asyncio
import json
import hashlib
import hmac
import time
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
from aiohttp import ClientTimeout, ClientError

logger = logging.getLogger(__name__)


class WebhookPlatform(Enum):
    """Webhook平台枚举"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECHAT_WORK = "wechat_work"
    SLACK = "slack"
    DISCORD = "discord"
    CUSTOM = "custom"


class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    MARKDOWN = "markdown"
    INTERACTIVE = "interactive"
    CARD = "card"
    CUSTOM = "custom"


@dataclass
class WebhookConfig:
    """Webhook配置类"""
    url: str
    platform: WebhookPlatform = WebhookPlatform.FEISHU
    secret: Optional[str] = None  # 用于签名验证的密钥
    timeout: int = 10  # 请求超时时间（秒）
    retry_count: int = 3  # 重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    enable_rate_limit: bool = True  # 是否启用请求限流
    max_requests_per_minute: int = 30  # 每分钟最大请求数
    custom_headers: Dict[str, str] = field(default_factory=dict)  # 自定义请求头
    enabled: bool = True  # 是否启用通知


@dataclass
class WebhookMessage:
    """Webhook消息类"""
    content: str
    msg_type: MessageType = MessageType.TEXT
    title: Optional[str] = None
    mentioned_users: List[str] = field(default_factory=list)  # @用户列表
    mentioned_all: bool = False  # 是否@所有人
    custom_data: Dict[str, Any] = field(default_factory=dict)  # 自定义数据
    priority: int = 1  # 消息优先级（1-5，5最高）


class RateLimiter:
    """请求限流器"""

    def __init__(self, max_requests_per_minute: int = 30):
        self.max_requests = max_requests_per_minute
        self.requests = []
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """获取请求许可"""
        async with self.lock:
            now = time.time()
            # 清理一分钟前的请求记录
            self.requests = [req_time for req_time in self.requests if now - req_time < 60]

            if len(self.requests) >= self.max_requests:
                return False

            self.requests.append(now)
            return True

    async def wait_if_needed(self):
        """如果需要，等待到可以发送请求"""
        while not await self.acquire():
            await asyncio.sleep(1)


class WebhookUtil:
    """Webhook通知工具类"""

    def __init__(self, config: Optional[WebhookConfig] = None):
        self.config = config
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self._background_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(f"WebhookUtil initialized for platform: {config.platform if config else 'None'}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()

    async def start(self):
        """启动webhook服务"""
        if self._running:
            return

        self.session = aiohttp.ClientSession(
            timeout=ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(limit=10)
        )

        self._running = True
        self._background_task = asyncio.create_task(self._background_sender())

        logger.info("WebhookUtil started")

    async def stop(self):
        """停止webhook服务"""
        if not self._running:
            return

        self._running = False

        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        if self.session:
            await self.session.close()

        logger.info("WebhookUtil stopped")

    def _get_rate_limiter(self, webhook_url: str) -> RateLimiter:
        """获取或创建限流器"""
        if webhook_url not in self.rate_limiters:
            max_requests = self.config.max_requests_per_minute if self.config else 30
            self.rate_limiters[webhook_url] = RateLimiter(max_requests)
        return self.rate_limiters[webhook_url]

    def _format_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """根据平台格式化消息"""
        if not self.config:
            return {"text": message.content}

        if self.config.platform == WebhookPlatform.FEISHU:
            return self._format_feishu_message(message)
        elif self.config.platform == WebhookPlatform.DINGTALK:
            return self._format_dingtalk_message(message)
        elif self.config.platform == WebhookPlatform.WECHAT_WORK:
            return self._format_wechat_work_message(message)
        elif self.config.platform == WebhookPlatform.SLACK:
            return self._format_slack_message(message)
        elif self.config.platform == WebhookPlatform.CUSTOM:
            return self._format_custom_message(message)
        else:
            return {"text": message.content}

    def _format_feishu_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """格式化飞书消息"""
        if message.msg_type == MessageType.TEXT:
            content = {"text": message.content}
        elif message.msg_type == MessageType.MARKDOWN:
            content = {"text": message.content}
        elif message.msg_type == MessageType.INTERACTIVE:
            content = message.custom_data
        else:
            content = {"text": message.content}

        return {
            "msg_type": message.msg_type.value,
            "content": content
        }

    def _format_dingtalk_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """格式化钉钉消息"""
        if message.msg_type == MessageType.TEXT:
            text = message.content
            if message.mentioned_all:
                text = f"@所有人 {text}"
            for user in message.mentioned_users:
                text = f"@{user} {text}"

            return {
                "msgtype": "text",
                "text": {"content": text}
            }
        elif message.msg_type == MessageType.MARKDOWN:
            return {
                "msgtype": "markdown",
                "markdown": {"title": message.title or "通知", "text": message.content}
            }
        else:
            return {"msgtype": "text", "text": {"content": message.content}}

    def _format_wechat_work_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """格式化企业微信消息"""
        return {
            "msgtype": "text",
            "text": {"content": message.content}
        }

    def _format_slack_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """格式化Slack消息"""
        return {
            "text": message.content,
            "username": "Trading Bot",
            "icon_emoji": ":chart_with_upwards_trend:"
        }

    def _format_custom_message(self, message: WebhookMessage) -> Dict[str, Any]:
        """格式化自定义消息"""
        return message.custom_data or {"text": message.content}

    def _generate_signature(self, timestamp: int) -> Optional[str]:
        """生成签名（用于飞书webhook验证）"""
        if not self.config or not self.config.secret:
            return None

        string_to_sign = f"{timestamp}\n{self.config.secret}"
        hmac_code = hmac.new(
            self.config.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        return hmac_code.hexdigest()

    def _prepare_headers(self, timestamp: int) -> Dict[str, str]:
        """准备请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ProCryptoTrader-Webhook/1.0"
        }

        # 添加自定义头部
        if self.config and self.config.custom_headers:
            headers.update(self.config.custom_headers)

        # 添加签名（飞书）
        if self.config and self.config.platform == WebhookPlatform.FEISHU and self.config.secret:
            signature = self._generate_signature(timestamp)
            if signature:
                headers["X-Lark-Request-Timestamp"] = str(timestamp)
                headers["X-Lark-Signature"] = signature

        return headers

    async def send_message(self, message: Union[str, WebhookMessage],
                          webhook_url: Optional[str] = None) -> bool:
        """
        发送webhook消息

        Args:
            message: 消息内容，可以是字符串或WebhookMessage对象
            webhook_url: webhook URL，如果为None则使用配置中的URL

        Returns:
            bool: 是否发送成功
        """
        if not self.config and not webhook_url:
            logger.warning("No webhook config or URL provided")
            return False

        if not self._running:
            logger.warning("WebhookUtil not started")
            return False

        # 构建消息对象
        if isinstance(message, str):
            message = WebhookMessage(content=message)

        # 使用指定的URL或配置中的URL
        url = webhook_url or (self.config.url if self.config else "")
        if not url:
            logger.warning("No webhook URL provided")
            return False

        # 检查是否启用
        if self.config and not self.config.enabled:
            logger.debug("Webhook notification disabled")
            return False

        # 添加到队列（异步发送）
        await self.message_queue.put((url, message, time.time()))

        return True

    async def _send_message_direct(self, url: str, message: WebhookMessage) -> bool:
        """
        直接发送消息（内部方法）

        Args:
            url: webhook URL
            message: 消息对象

        Returns:
            bool: 是否发送成功
        """
        # 限流检查
        if self.config and self.config.enable_rate_limit:
            rate_limiter = self._get_rate_limiter(url)
            await rate_limiter.wait_if_needed()

        # 格式化消息
        payload = self._format_message(message)

        # 准备请求头
        timestamp = int(time.time())
        headers = self._prepare_headers(timestamp)

        retry_count = self.config.retry_count if self.config else 3
        retry_delay = self.config.retry_delay if self.config else 1.0

        for attempt in range(retry_count + 1):
            try:
                if not self.session:
                    logger.error("HTTP session not initialized")
                    return False

                async with self.session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        logger.debug(f"Webhook message sent successfully to {url}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.warning(f"Webhook failed with status {response.status}: {error_text}")

                        # 如果不是服务器错误，不重试
                        if response.status < 500:
                            return False

            except (ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Webhook attempt {attempt + 1} failed: {e}")

                if attempt < retry_count:
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # 指数退避
                else:
                    logger.error(f"Webhook failed after {retry_count + 1} attempts")
                    return False

        return False

    async def _background_sender(self):
        """后台消息发送任务"""
        logger.info("Background webhook sender started")

        while self._running:
            try:
                # 从队列获取消息
                url, message, timestamp = await asyncio.wait_for(
                    self.message_queue.get(), timeout=1.0
                )

                # 检查消息是否过期（30秒）
                if time.time() - timestamp > 30:
                    logger.warning("Webhook message expired, skipping")
                    continue

                # 异步发送消息
                asyncio.create_task(self._send_message_direct(url, message))

            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
            except Exception as e:
                logger.error(f"Background sender error: {e}")
                await asyncio.sleep(1)

        logger.info("Background webhook sender stopped")

    async def send_trading_signal(self, symbol: str, signal_type: str,
                                 price: float, confidence: float,
                                 strategy_name: str = "TickBreakout",
                                 timestamp: Optional[str] = None) -> bool:
        """
        发送交易信号通知

        Args:
            symbol: 交易对符号
            signal_type: 信号类型（BUY/SELL）
            price: 价格
            confidence: 信号置信度
            strategy_name: 策略名称
            timestamp: 可选的时间戳，如果不提供则使用当前时间

        Returns:
            bool: 是否发送成功
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建消息内容
        content = f"""🚀 交易信号通知
📈 交易对: {symbol}
📊 信号类型: {signal_type}
💰 当前价格: ${price:.6f}
🎯 置信度: {confidence:.2%}
🤖 策略: {strategy_name}
⏰ 时间: {timestamp}"""

        message = WebhookMessage(
            content=content,
            msg_type=MessageType.TEXT,
            priority=4,  # 高优先级
            title=f"交易信号 - {symbol}"
        )

        return await self.send_message(message)

    async def send_alert(self, title: str, message: str,
                        level: str = "INFO") -> bool:
        """
        发送告警通知

        Args:
            title: 告警标题
            message: 告警内容
            level: 告警级别（INFO/WARNING/ERROR/CRITICAL）

        Returns:
            bool: 是否发送成功
        """
        # 根据级别添加表情符号
        level_emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨"
        }.get(level, "ℹ️")

        content = f"""{level_emoji} {title}
{message}
⏰ 时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""

        webhook_message = WebhookMessage(
            content=content,
            msg_type=MessageType.TEXT,
            priority=5 if level == "CRITICAL" else 3,
            title=f"{level_emoji} {level} - {title}"
        )

        return await self.send_message(webhook_message)


# 全局webhook实例（单例）
_global_webhook: Optional[WebhookUtil] = None


def get_webhook(config: Optional[WebhookConfig] = None) -> WebhookUtil:
    """
    获取全局webhook实例

    Args:
        config: webhook配置，只在第一次调用时有效

    Returns:
        WebhookUtil: webhook工具实例
    """
    global _global_webhook
    if _global_webhook is None:
        _global_webhook = WebhookUtil(config)
    return _global_webhook


# 便捷函数
async def send_trading_signal(symbol: str, signal_type: str, price: float,
                            confidence: float, strategy_name: str = "TickBreakout",
                            timestamp: Optional[str] = None) -> bool:
    """便捷函数：发送交易信号"""
    webhook = get_webhook()
    return await webhook.send_trading_signal(symbol, signal_type, price, confidence, strategy_name, timestamp)


async def send_alert(title: str, message: str, level: str = "INFO") -> bool:
    """便捷函数：发送告警"""
    webhook = get_webhook()
    return await webhook.send_alert(title, message, level)


async def send_message(content: str, webhook_url: Optional[str] = None) -> bool:
    """便捷函数：发送简单消息"""
    webhook = get_webhook()
    return await webhook.send_message(content, webhook_url)


# 预定义的webhook配置
FEISHU_WEBHOOK_CONFIG = WebhookConfig(
    url="https://open.feishu.cn/open-apis/bot/v2/hook/c3ff3aea-4700-4694-95a5-b07922d90def",
    platform=WebhookPlatform.FEISHU,
    timeout=10,
    retry_count=3,
    enable_rate_limit=True,
    max_requests_per_minute=30
)


# 使用示例
if __name__ == "__main__":
    async def test_webhook():
        # 创建配置
        config = FEISHU_WEBHOOK_CONFIG

        # 使用异步上下文管理器
        async with WebhookUtil(config) as webhook:
            # 发送交易信号
            await webhook.send_trading_signal(
                symbol="BTC/USDT",
                signal_type="BUY",
                price=45000.0,
                confidence=0.85,
                strategy_name="TickBreakout"
            )

            # 发送告警
            await webhook.send_alert(
                title="系统启动",
                message="高频交易系统已成功启动",
                level="INFO"
            )

            # 发送简单消息
            await webhook.send_message("测试消息：这是一条测试通知")

            # 等待消息发送完成
            await asyncio.sleep(5)

    # 运行测试
    asyncio.run(test_webhook())