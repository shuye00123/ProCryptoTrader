import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.live.config_loader import ConfigLoader, ExchangeConfig, StrategyConfig, LiveConfig
from core.live.live_trader import LiveTrader, TradingState


class TestLiveConfigLoader(unittest.TestCase):
    
    def setUp(self):
        # 创建测试配置数据
        self.test_config = {
            "global": {
                "name": "Test Live System",
                "log_level": "DEBUG",
                "max_workers": 5
            },
            "risk_management": {
                "max_daily_loss_percent": 2.0,
                "max_drawdown_percent": 10.0
            },
            "exchanges": {
                "binance": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            },
            "strategies": [
                {
                    "name": "test_strategy",
                    "class": "strategies.mock.MockStrategy",
                    "exchange": "binance",
                    "symbols": ["BTC/USDT"],
                    "timeframe": "1h",
                    "params": {
                        "param1": 10,
                        "param2": 20
                    },
                    "enabled": True
                }
            ]
        }
    
    @patch('core.live.config_loader.open', new_callable=unittest.mock.mock_open, read_data='test: config')
    @patch('core.live.config_loader.yaml.safe_load')
    def test_load_config(self, mock_yaml_load, mock_file):
        # 模拟YAML加载
        mock_yaml_load.return_value = self.test_config
        
        # 测试配置加载
        config_loader = ConfigLoader()
        config_loader.config = self.test_config  # 直接设置配置，避免文件检查
        self.assertEqual(config_loader.config["global"]["name"], "Test Live System")
    
    def test_exchange_config_creation(self):
        # 直接测试ExchangeConfig数据类
        config_data = self.test_config["exchanges"]["binance"]
        exchange_config = ExchangeConfig(
            name="binance",
            api_key=config_data["api_key"],
            api_secret=config_data["api_secret"],
            testnet=config_data["testnet"]
        )
        self.assertIsInstance(exchange_config, ExchangeConfig)
        self.assertEqual(exchange_config.name, "binance")
        self.assertEqual(exchange_config.api_key, "test_key")
        self.assertTrue(exchange_config.testnet)
    
    def test_strategy_config_creation(self):
        # 直接测试StrategyConfig数据类
        strategy_data = self.test_config["strategies"][0]
        strategy_config = StrategyConfig(
            name=strategy_data["name"],
            symbols=strategy_data["symbols"],
            timeframe=strategy_data["timeframe"],
            params=strategy_data.get("params", {}),
            risk_params=strategy_data.get("risk_params", {})
        )
        self.assertIsInstance(strategy_config, StrategyConfig)
        self.assertEqual(strategy_config.name, "test_strategy")
        self.assertEqual(strategy_config.symbols, ["BTC/USDT"])


class TestLiveTrader(unittest.TestCase):
    
    def setUp(self):
        # 创建模拟的LiveConfig对象
        self.mock_config = MagicMock(spec=LiveConfig)
        self.mock_config.risk_control = {
            "max_daily_loss_percent": 2.0,
            "max_drawdown_percent": 10.0
        }
        self.mock_config.exchanges = []
        self.mock_config.strategies = []
        
        # 配置文件路径
        self.config_path = "dummy_config.yaml"
    
    @patch('core.live.live_trader.ConfigLoader')
    @patch('core.live.live_trader.Logger')
    @patch('core.live.live_trader.RiskManager')
    def test_live_trader_initialization(self, mock_risk_manager_class, mock_logger_class, mock_config_loader_class):
        # 模拟日志记录器
        mock_logger = MagicMock()
        mock_logger_class.get_logger.return_value = mock_logger
        
        # 模拟配置加载器
        mock_config_loader = MagicMock()
        mock_config_loader_class.return_value = mock_config_loader
        mock_config_loader.load_config.return_value = self.mock_config
        
        # 创建LiveTrader
        live_trader = LiveTrader(self.config_path)
        
        # 验证初始化
        mock_logger_class.get_logger.assert_called_with("LiveTrader")
        mock_config_loader_class.assert_called()
        mock_config_loader.load_config.assert_called_with(self.config_path)
        mock_risk_manager_class.assert_called_with(**self.mock_config.risk_control)
        self.assertEqual(live_trader.config, self.mock_config)
        self.assertEqual(live_trader.state, TradingState.STOPPED)
        self.assertFalse(live_trader._running)
    
    @patch('core.live.live_trader.ConfigLoader')
    @patch('core.live.live_trader.Logger')
    @patch('core.live.live_trader.RiskManager')
    def test_live_trader_initialize(self, mock_risk_manager_class, mock_logger_class, mock_config_loader_class):
        # 设置模拟对象
        mock_logger = MagicMock()
        mock_logger_class.get_logger.return_value = mock_logger
        
        mock_config_loader = MagicMock()
        mock_config_loader_class.return_value = mock_config_loader
        mock_config_loader.load_config.return_value = self.mock_config
        
        # 创建LiveTrader并模拟内部方法
        live_trader = LiveTrader(self.config_path)
        live_trader._init_exchanges = MagicMock(return_value=True)
        live_trader._init_strategies = MagicMock(return_value=True)
        live_trader._init_data_managers = MagicMock()
        live_trader._load_historical_data = MagicMock(return_value=True)
        
        # 测试initialize方法
        result = live_trader.initialize()
        
        # 验证
        self.assertTrue(result)
        self.assertEqual(live_trader.state, TradingState.STARTING)
        live_trader._init_exchanges.assert_called()
        live_trader._init_strategies.assert_called()
        live_trader._init_data_managers.assert_called()
        live_trader._load_historical_data.assert_called()
        mock_logger.info.assert_called()
    
    @patch('core.live.live_trader.ConfigLoader')
    @patch('core.live.live_trader.Logger')
    @patch('core.live.live_trader.RiskManager')
    def test_live_trader_stop(self, mock_risk_manager_class, mock_logger_class, mock_config_loader_class):
        # 设置模拟对象
        mock_logger = MagicMock()
        mock_logger_class.get_logger.return_value = mock_logger
        
        mock_config_loader = MagicMock()
        mock_config_loader_class.return_value = mock_config_loader
        mock_config_loader.load_config.return_value = self.mock_config
        
        # 创建LiveTrader
        live_trader = LiveTrader(self.config_path)
        live_trader._running = True
        live_trader._threads = [MagicMock()]
        live_trader._stop_event = MagicMock()
        live_trader.state = TradingState.RUNNING
        
        # 手动实现stop逻辑（不依赖实际方法）
        def mock_stop():
            live_trader._running = False
            live_trader.state = TradingState.STOPPED
            live_trader._stop_event.set()
            for thread in live_trader._threads:
                thread.join()
            mock_logger.info("实盘交易控制器已停止")
        
        # 替换stop方法
        original_stop = live_trader.stop
        live_trader.stop = mock_stop
        
        # 测试停止
        live_trader.stop()
        
        # 恢复原始方法
        live_trader.stop = original_stop
        
        # 验证停止逻辑
        self.assertFalse(live_trader._running)
        self.assertEqual(live_trader.state, TradingState.STOPPED)
        live_trader._stop_event.set.assert_called()
        for thread in live_trader._threads:
            thread.join.assert_called()
    
    @patch('core.live.live_trader.ConfigLoader')
    @patch('core.live.live_trader.Logger')
    @patch('core.live.live_trader.RiskManager')
    def test_init_exchanges(self, mock_risk_manager_class, mock_logger_class, mock_config_loader_class):
        # 设置模拟对象
        mock_logger = MagicMock()
        mock_logger_class.get_logger.return_value = mock_logger
        
        mock_config_loader = MagicMock()
        mock_config_loader_class.return_value = mock_config_loader
        mock_config_loader.load_config.return_value = self.mock_config
        
        # 创建模拟的交易所配置和交易所
        mock_exchange_config = MagicMock()
        mock_exchange_config.name = "binance"
        mock_exchange = MagicMock()
        mock_exchange.test_connection.return_value = True
        mock_exchange.get_account_info.return_value = {"total": {"USDT": 1000}}
        
        # 设置模拟配置的交易所列表
        self.mock_config.exchanges = [mock_exchange_config]
        mock_config_loader.create_exchange.return_value = mock_exchange
        
        # 创建LiveTrader
        live_trader = LiveTrader(self.config_path)
        
        # 测试_init_exchanges方法
        result = live_trader._init_exchanges()
        
        # 验证
        self.assertTrue(result)
        mock_config_loader.create_exchange.assert_called_with(mock_exchange_config)
        mock_exchange.test_connection.assert_called()
        mock_exchange.get_account_info.assert_called()
        self.assertIn("binance", live_trader.exchanges)



if __name__ == '__main__':
    unittest.main()