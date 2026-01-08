"""
使用生产代码的实际算法逻辑重新分析GUNUSDT/BABYUSDT数据

目的: 验证为什么测试脚本显示有信号，但生产代码不触发webhook
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

print('='*80)
print('生产代码算法逻辑验证')
print('='*80)

# ============================================================================
# 1. 加载数据
# ============================================================================

print('\n[加载数据]')

gunusdt_file = Path('data/tick/binance/GUNUSDT_2026010716.parquet')
babyusdt_file = Path('data/tick/binance/BABYUSDT_2026010721.parquet')

if gunusdt_file.exists():
    gunusdt_df = pd.read_parquet(gunusdt_file)
    gunusdt_df['event_time_pd'] = pd.to_datetime(gunusdt_df['event_time'])
    gunusdt_df['volume_increment'] = gunusdt_df['volume'].diff().fillna(0)
    print(f'  GUNUSDT: {len(gunusdt_df)} rows')

if babyusdt_file.exists():
    babyusdt_df = pd.read_parquet(babyusdt_file)
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df['volume_increment'] = babyusdt_df['volume'].diff().fillna(0)
    print(f'  BABYUSDT: {len(babyusdt_df)} rows')

# ============================================================================
# 2. 定义生产代码的算法逻辑（简化版）
# ============================================================================

print('\n[算法配置]')

# 生产代码配置 (fc3ab00版本 - 运行了一天只产生2个webhook信号的配置)
CONFIG_FC3AB00 = {
    'statistical_breakout': {
        'price_deviation_threshold': 3.5,
        'momentum_ratio_threshold': 2.5,
        'min_sample_size': 200
    },
    'volume_breakout': {
        'volume_surge_threshold': 1.2,
        'min_price_change': 0.005,
        'min_avg_volume': 1,
        'min_data_points': 100
    },
    'consecutive_breakout': {
        'min_consecutive_moves': 2,
        'min_move_threshold': 0.001
    },
    'direction_coordination': {
        'enabled': True,
        'min_consensus_score': 0.65,
        'algorithm_weights': {
            'STATISTICAL': 0.25,
            'MOMENTUM': 0.1,
            'CONSECUTIVE': 0.1,
            'VOLUME': 0.35,
            'PATH': 0.2
        }
    },
    'require_multiple_confirmation': True,
    'min_confirmation_count': 2,
    'confirmation_window': 5000
}

# 生产代码配置 (530ccd4版本 - 更严格的配置)
CONFIG_530CCD4 = {
    'statistical_breakout': {
        'price_deviation_threshold': 2.5,  # 降低
        'momentum_ratio_threshold': 2.5,
        'min_sample_size': 200
    },
    'volume_breakout': {
        'volume_surge_threshold': 2.0,  # 提高
        'min_price_change': 0.005,
        'min_avg_volume': 1,
        'min_data_points': 100
    },
    'consecutive_breakout': {
        'min_consecutive_moves': 5,  # 提高
        'min_move_threshold': 0.001
    },
    'direction_coordination': {
        'enabled': True,
        'min_consensus_score': 0.65,
        'algorithm_weights': {
            'STATISTICAL': 0.25,
            'MOMENTUM': 0.1,
            'CONSECUTIVE': 0.1,
            'VOLUME': 0.35,
            'PATH': 0.2
        }
    },
    'require_multiple_confirmation': True,
    'min_confirmation_count': 3,  # 提高
    'confirmation_window': 5000
}

print('  配置版本1: fc3ab00 (运行了一天的配置)')
print('  配置版本2: 530ccd4 (更严格的配置)')

# ============================================================================
# 3. 实现生产代码的算法检测逻辑
# ============================================================================

class ProductionAlgorithmDetector:
    """模拟生产代码的算法检测逻辑"""

    def __init__(self, config):
        self.config = config
        self.window_size = 200
        self.pending_signals = {}  # 确认窗口

    def detect_statistical_breakout(self, prices, i, volumes):
        """统计突破检测"""
        if i < self.window_size:
            return None

        window_prices = prices[i-self.window_size:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)

        if std_price == 0:
            return None

        z_score = (prices[i] - mean_price) / std_price

        threshold = self.config['statistical_breakout']['price_deviation_threshold']
        if abs(z_score) >= threshold:
            return {
                'type': 'STATISTICAL',
                'z_score': z_score,
                'strength': abs(z_score),
                'direction': 'BUY' if z_score > 0 else 'SELL'
            }
        return None

    def detect_volume_breakout(self, prices, i, volumes):
        """成交量突破检测"""
        if i < self.window_size:
            return None

        window_volumes = np.array(volumes[i-self.window_size:i])
        avg_volume = np.mean(window_volumes[window_volumes > 0])

        if avg_volume == 0:
            return None

        volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0
        price_change = abs(prices[i] - prices[i-1]) / prices[i-1] if i > 0 else 0

        threshold = self.config['volume_breakout']['volume_surge_threshold']
        min_price_change = self.config['volume_breakout']['min_price_change']

        if volume_ratio >= threshold and price_change >= min_price_change:
            return {
                'type': 'VOLUME',
                'volume_ratio': volume_ratio,
                'strength': volume_ratio,
                'direction': 'BUY' if prices[i] > prices[i-1] else 'SELL'
            }
        return None

    def detect_consecutive_breakout(self, prices, i, volumes):
        """连续变动突破检测"""
        if i < self.config['consecutive_breakout']['min_consecutive_moves']:
            return None

        min_moves = self.config['consecutive_breakout']['min_consecutive_moves']
        min_threshold = self.config['consecutive_breakout']['min_move_threshold']

        # 检查最近min_moves次变动
        consecutive_up = 0
        consecutive_down = 0

        for j in range(i - min_moves + 1, i + 1):
            if j > 0:
                change = (prices[j] - prices[j-1]) / prices[j-1]
                if change > min_threshold:
                    consecutive_up += 1
                elif change < -min_threshold:
                    consecutive_down += 1

        if consecutive_up >= min_moves:
            return {
                'type': 'CONSECUTIVE',
                'consecutive_moves': consecutive_up,
                'strength': consecutive_up,
                'direction': 'BUY'
            }
        elif consecutive_down >= min_moves:
            return {
                'type': 'CONSECUTIVE',
                'consecutive_moves': consecutive_down,
                'strength': consecutive_down,
                'direction': 'SELL'
            }
        return None

    def calculate_direction_consensus(self, detections):
        """计算方向共识（模拟DirectionCoordinator）"""
        if not detections:
            return None

        weights = self.config['direction_coordination']['algorithm_weights']

        buy_weight = 0.0
        sell_weight = 0.0

        for detection in detections:
            algo_type = detection['type']
            weight = weights.get(algo_type, 0.2)

            if detection['direction'] == 'BUY':
                buy_weight += weight
            else:
                sell_weight += weight

        total_weight = buy_weight + sell_weight
        if total_weight == 0:
            return None

        consensus_score = abs(buy_weight - sell_weight) / 1.0  # 总权重是1.0
        direction = 'BUY' if buy_weight > sell_weight else 'SELL'

        return {
            'consensus_score': consensus_score,
            'direction': direction,
            'buy_weight': buy_weight,
            'sell_weight': sell_weight
        }

    def process_tick(self, price, volume, timestamp, symbol):
        """处理单个tick（模拟生产代码主逻辑）"""
        i = len(self.price_history)

        self.price_history.append(price)
        self.volume_history.append(volume)

        # 收集算法检测结果
        detections = []

        stat_detection = self.detect_statistical_breakout(self.price_history, i, self.volume_history)
        if stat_detection:
            detections.append(stat_detection)

        vol_detection = self.detect_volume_breakout(self.price_history, i, self.volume_history)
        if vol_detection:
            detections.append(vol_detection)

        con_detection = self.detect_consecutive_breakout(self.price_history, i, self.volume_history)
        if con_detection:
            detections.append(con_detection)

        if not detections:
            return None

        # 计算方向共识
        consensus = self.calculate_direction_consensus(detections)

        if consensus is None:
            return None

        # 检查共识分数
        min_consensus = self.config['direction_coordination']['min_consensus_score']
        if consensus['consensus_score'] < min_consensus:
            return {
                'filtered': True,
                'reason': f'CONSENSUS_TOO_LOW: {consensus["consensus_score"]:.3f} < {min_consensus}',
                'detections': detections,
                'consensus': consensus
            }

        # 通过过滤！
        return {
            'filtered': False,
            'detections': detections,
            'consensus': consensus,
            'timestamp': timestamp
        }

    def reset(self):
        """重置状态"""
        self.price_history = []
        self.volume_history = []

# ============================================================================
# 4. 运行验证
# ============================================================================

print('\n' + '='*80)
print('验证结果')
print('='*80)

def validate_with_config(df, symbol, config, config_name):
    """使用指定配置验证数据"""
    print(f'\n[{symbol}] - {config_name}')
    print('-'*80)

    detector = ProductionAlgorithmDetector(config)
    detector.reset()

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    stats = {
        'total_ticks': len(prices),
        'statistical_hits': 0,
        'volume_hits': 0,
        'consecutive_hits': 0,
        'consensus_pass': 0,
        'consensus_fail': 0,
        'final_signals': 0
    }

    filtered_signals = []

    for i in range(len(prices)):
        result = detector.process_tick(prices[i], volumes[i], times[i], symbol)

        if result is None:
            continue

        # 统计算法命中
        for detection in result.get('detections', []):
            if detection['type'] == 'STATISTICAL':
                stats['statistical_hits'] += 1
            elif detection['type'] == 'VOLUME':
                stats['volume_hits'] += 1
            elif detection['type'] == 'CONSECUTIVE':
                stats['consecutive_hits'] += 1

        if result.get('filtered'):
            stats['consensus_fail'] += 1
            filtered_signals.append(result)
        else:
            stats['consensus_pass'] += 1
            stats['final_signals'] += 1

    # 打印统计
    print(f'  总tick数: {stats["total_ticks"]}')
    print(f'  STATISTICAL算法命中: {stats["statistical_hits"]} 次')
    print(f'  VOLUME算法命中: {stats["volume_hits"]} 次')
    print(f'  CONSECUTIVE算法命中: {stats["consecutive_hits"]} 次')
    print(f'  方向共识通过: {stats["consensus_pass"]} 次')
    print(f'  方向共识失败: {stats["consensus_fail"]} 次')
    print(f'  最终生成信号: {stats["final_signals"]} 次')

    # 分析被过滤的信号
    if filtered_signals:
        print(f'\n  被过滤信号分析（前5个）:')
        for i, signal in enumerate(filtered_signals[:5]):
            consensus = signal['consensus']
            print(f'    {i+1}. 共识分数: {consensus["consensus_score"]:.3f}, '
                  f'买入权重: {consensus["buy_weight"]:.2f}, '
                  f'卖出权重: {consensus["sell_weight"]:.2f}, '
                  f'原因: {signal["reason"]}')

    return stats, filtered_signals

# 验证GUNUSDT
if 'gunusdt_df' in locals():
    print('\n' + '='*80)
    print('GUNUSDT 验证')
    print('='*80)

    stats_fc3, filtered_fc3 = validate_with_config(
        gunusdt_df, 'GUNUSDT', CONFIG_FC3AB00, 'fc3ab00配置'
    )

    stats_530, filtered_530 = validate_with_config(
        gunusdt_df, 'GUNUSDT', CONFIG_530CCD4, '530ccd4配置'
    )

# 验证BABYUSDT
if 'babyusdt_df' in locals():
    print('\n' + '='*80)
    print('BABYUSDT 验证')
    print('='*80)

    stats_fc3_baby, filtered_fc3_baby = validate_with_config(
        babyusdt_df, 'BABYUSDT', CONFIG_FC3AB00, 'fc3ab00配置'
    )

    stats_530_baby, filtered_530_baby = validate_with_config(
        babyusdt_df, 'BABYUSDT', CONFIG_530CCD4, '530ccd4配置'
    )

# ============================================================================
# 5. 总结
# ============================================================================

print('\n' + '='*80)
print('验证总结')
print('='*80)

print('\n🔴 关键发现:')
print('  1. 测试脚本只检测了Z-Score和Volume Ratio 2个条件')
print('  2. 生产代码实现了5个算法 + 方向协调机制')
print('  3. 方向协调机制的min_consensus_score=0.65非常严格')
print('  4. 即使单个算法命中，共识分数也可能<0.65而被过滤')

print('\n💡 建议:')
print('  1. 降低min_consensus_score到0.45（推荐）')
print('  2. 或关闭direction_coordination（激进）')
print('  3. 添加详细日志记录算法触发情况')

print('\n' + '='*80)
print('验证完成')
print('='*80)
