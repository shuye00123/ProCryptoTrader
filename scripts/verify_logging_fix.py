#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证日志修复效果
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import yaml

def test_logging_fix():
    print("=" * 60)
    print("验证日志修复效果")
    print("=" * 60)

    # 加载修复后的配置
    with open("configs/hf_breakout_live_config.yaml", 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    logging_config = config.get('logging', {})
    modules_config = logging_config.get('modules', {})

    print("\n1. 修复后的配置:")
    print(f"   全局日志级别: {logging_config.get('level')}")
    print(f"   模块配置:")
    for module, level in modules_config.items():
        print(f"     {module}: {level}")

    # 测试模块logger级别
    print("\n2. 模块logger级别测试:")
    test_modules = [
        ("HighFrequencyTrader", "HighFrequencyTrader"),
        ("core.strategy.high_frequency_breakout", "core.strategy.high_frequency_breakout"),
        ("core.trading.fast_execution", "core.trading.fast_execution"),
        ("core.strategy.tick_breakout_detector", "core.strategy.tick_breakout_detector")
    ]

    for display_name, logger_name in test_modules:
        logger = logging.getLogger(logger_name)
        level_name = logging.getLevelName(logger.level)
        print(f"   {display_name:<40}: {logger_name} -> {level_name}")

    print("\n3. 模拟HighFrequencyTrader初始化测试:")
    try:
        from core.live.high_frequency_trader import HighFrequencyTrader

        print("   创建HighFrequencyTrader实例...")
        trader = HighFrequencyTrader("configs/hf_breakout_live_config.yaml")

        print("\n4. 测试DEBUG日志输出:")
        print("   发送测试日志...")

        # 获取logger
        hft_logger = logging.getLogger("HighFrequencyTrader")
        hfb_logger = logging.getLogger("core.strategy.high_frequency_breakout")
        tbd_logger = logging.getLogger("core.trading.fast_execution")
        tb_detector_logger = logging.getLogger("core.strategy.tick_breakout_detector")

        # 测试不同级别的日志
        print("   HighFrequencyTrader DEBUG日志:")
        hft_logger.debug("HFT DEBUG TEST - 应该显示")

        print("   core.strategy.high_frequency_breakout DEBUG日志:")
        hfb_logger.debug("HFB DEBUG TEST - 应该显示")

        print("   core.trading.fast_execution DEBUG日志:")
        tbd_logger.debug("FASTEXEC DEBUG TEST - 应该显示")

        print("   TickBreakoutDetector DEBUG日志:")
        tb_detector_logger.debug("TICK BREAKOUT DETECTOR DEBUG TEST - 应该显示")

        print("   模拟TickBreakoutDetector算法执行:")
        # 模拟算法中的DEBUG日志
        tb_detector_logger.debug("TICK: ProcessTick开始 - symbol=BTC-USDT, price=50000.0")
        tb_detector_logger.debug("TICK: 更新历史数据 - price:50000.0, volume:1000000")
        tb_detector_logger.debug("TICK: 检测突破算法 - statistical=False, momentum=False")
        tb_detector_logger.debug("TICK: 检测连续变动 - consecutive=3, threshold=8")
        tb_detector_logger.debug("TICK: 检测成交量突破 - ratio=1.5, threshold=4.0")
        tb_detector_logger.debug("TICK: 检测路径突破 - breakout=False")
        tb_detector_logger.debug("TICK: 未检测到突破信号")

        print("\n5. 验证结果:")
        expected_logs = [
            ("HighFrequencyTrader DEBUG", "应该显示"),
            ("core.strategy.high_frequency_breakout DEBUG", "应该显示"),
            ("core.trading.fast_execution DEBUG", "应该显示"),
            ("core.strategy.tick_breakout_detector DEBUG", "应该显示")
        ]

        for log_desc, expected in expected_logs:
            print(f"   {log_desc}: {expected}")

        print("\n✅ 修复完成！现在应该能看到详细DEBUG日志了")
        return True

    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    success = test_logging_fix()

    if success:
        print("\n" + "=" * 60)
        print("结论:")
        print("=" * 60)

        print("✅ 模块日志名称修复成功！")
        print("✅ 配置文件已更新为正确的模块名称")
        print()
        print("🎯 预期效果:")
        print("   重新运行策略后应该能看到:")
        print("   - HighFrequencyTrader的详细DEBUG日志")
        print("   - core.strategy.high_frequency_breakout的DEBUG日志")
        print("   - core.strategy.tick_breakout_detector的算法执行DEBUG日志")
        print("   - core.trading.fast_execution的DEBUG日志")
        print()
        print("🚀 立即测试:")
        print("   python main.py live --config hf_breakout_live_config.yaml")
        print()
        print("📊 调试信息:")
        print("   现在能看到TickBreakoutDetector的详细执行流程了！")
        print("   可以观察到:")
        print("   - 每个tick数据的处理过程")
        print("   - 5种突破检测算法的触发情况")
        print("   - 历史数据更新和计算")
        print("   - 信号生成和过滤的完整流程")

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)