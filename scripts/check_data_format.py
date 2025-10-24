#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查下载的数据格式和内容
"""

import os
import sys
from pathlib import Path
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_btc_data():
    """检查BTC数据格式"""
    print("=" * 60)
    print("检查Binance BTC/USDT数据格式")
    print("=" * 60)

    btc_file = project_root / "data" / "binance" / "BTC-USDT" / "1d.parquet"

    if not btc_file.exists():
        print(f"❌ 数据文件不存在: {btc_file}")
        return False

    try:
        # 读取数据
        df = pd.read_parquet(btc_file)
        print(f"✓ 成功读取数据文件")
        print(f"数据形状: {df.shape}")
        print(f"列名: {list(df.columns)}")
        print(f"索引类型: {type(df.index)}")

        # 检查索引
        if isinstance(df.index, pd.DatetimeIndex):
            print(f"✓ 时间索引正确")
            print(f"时间范围: {df.index.min()} 至 {df.index.max()}")
            print(f"数据天数: {len(df)} 天")
        else:
            print(f"❌ 索引不是时间类型")
            return False

        # 检查数据类型
        print(f"\n📊 数据类型:")
        for col in df.columns:
            print(f"  {col}: {df[col].dtype}")

        # 检查数据完整性
        print(f"\n🔍 数据完整性检查:")
        missing_values = df.isnull().sum()
        if missing_values.sum() == 0:
            print("✓ 无缺失值")
        else:
            print(f"⚠️  缺失值: {missing_values.to_dict()}")

        # 检查价格逻辑
        price_errors = 0
        for idx, row in df.iterrows():
            if not (row['low'] <= row['open'] <= row['high'] and
                   row['low'] <= row['close'] <= row['high']):
                price_errors += 1

        if price_errors == 0:
            print("✓ 价格数据逻辑正确")
        else:
            print(f"❌ 发现 {price_errors} 条价格逻辑错误")

        # 显示基本统计
        print(f"\n📈 基本统计:")
        print(f"  价格范围: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")
        print(f"  平均价格: ${df['close'].mean():,.2f}")
        print(f"  平均成交量: {df['volume'].mean():,.0f}")

        # 显示前几行和后几行
        print(f"\n📋 数据示例:")
        print("前5行:")
        print(df.head())
        print("\n后5行:")
        print(df.tail())

        return True

    except Exception as e:
        print(f"❌ 读取数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_data_loader_compatibility():
    """检查与DataLoader的兼容性"""
    print(f"\n" + "=" * 60)
    print("检查DataLoader兼容性")
    print("=" * 60)

    try:
        from core.data.data_loader import DataLoader

        # 创建DataLoader
        data_dir = project_root / "data" / "binance"
        loader = DataLoader(str(data_dir))

        # 测试加载BTC数据
        print("测试加载BTC/USDT 1d数据...")
        data = loader.load_data(
            symbol="BTC/USDT",
            timeframe="1d",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )

        if data is not None and not data.empty:
            print(f"✓ DataLoader兼容性测试成功")
            print(f"加载的数据量: {len(data)} 条")
            print(f"时间范围: {data.index.min()} 至 {data.index.max()}")
            print(f"数据列: {list(data.columns)}")
            return True
        else:
            print(f"❌ DataLoader返回空数据")
            return False

    except Exception as e:
        print(f"❌ DataLoader兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    success = True

    # 检查数据格式
    if not check_btc_data():
        success = False

    # 检查DataLoader兼容性
    if not check_data_loader_compatibility():
        success = False

    if success:
        print(f"\n🎉 数据格式检查完成！所有检查都通过。")
        print(f"数据已准备好用于回测。")
    else:
        print(f"\n❌ 数据格式检查发现问题，需要修复。")

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)