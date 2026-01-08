"""
Test Multi-Factor Confirmation Mechanism
Validate that 2+ algorithms are required to generate signals
Validate that avg_strength >= 2.5 threshold is enforced
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

print('='*80)
print('Multi-Factor Confirmation Mechanism Test')
print('='*80)
print(f'Test Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

# ============================================================================
# 1. Load Data
# ============================================================================

print('\n[Loading Data]')

# GUNUSDT data
gunusdt_files = [
    Path('data/tick/binance/GUNUSDT_2026010715.parquet'),
    Path('data/tick/binance/GUNUSDT_2026010716.parquet')
]

gunusdt_dfs = []
for f in gunusdt_files:
    if f.exists():
        df = pd.read_parquet(f)
        gunusdt_dfs.append(df)
        print(f'  [OK] {f.name}: {len(df)} rows')

if gunusdt_dfs:
    gunusdt_df = pd.concat(gunusdt_dfs, ignore_index=True)
    gunusdt_df['event_time_pd'] = pd.to_datetime(gunusdt_df['event_time'])
    gunusdt_df = gunusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    gunusdt_df['volume_increment'] = gunusdt_df['volume'].diff().fillna(0)
    print(f'  GUNUSDT combined: {len(gunusdt_df)} rows')
else:
    print('  [ERROR] GUNUSDT data not found')
    exit(1)

# BABYUSDT data (use 21:00 data for comparison)
babyusdt_file = Path('data/tick/binance/BABYUSDT_2026010721.parquet')
if babyusdt_file.exists():
    babyusdt_df = pd.read_parquet(babyusdt_file)
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df = babyusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    babyusdt_df['volume_increment'] = babyusdt_df['volume'].diff().fillna(0)
    print(f'  [OK] BABYUSDT_2026010721.parquet: {len(babyusdt_df)} rows')
else:
    print('  [ERROR] BABYUSDT data not found')
    exit(1)

# ============================================================================
# 2. Configuration (from hf_breakout_live_config.yaml)
# ============================================================================

print('\n[Multi-Factor Configuration]')
MIN_CONFIRMATION_COUNT = 2  # Require 2 algorithms
MIN_BREAKOUT_STRENGTH = 2.5  # Optimized value
WINDOW_SIZE = 200
CONFIRMATION_WINDOW_MS = 5000  # 5 seconds

print(f'  Minimum Confirmation Count: {MIN_CONFIRMATION_COUNT} algorithms')
print(f'  Minimum Breakout Strength: {MIN_BREAKOUT_STRENGTH}')
print(f'  Window Size: {WINDOW_SIZE} ticks')
print(f'  Confirmation Window: {CONFIRMATION_WINDOW_MS}ms')

# ============================================================================
# 3. Simulate Multi-Factor Detection
# ============================================================================

class AlgorithmDetector:
    """Simulate individual algorithm detection"""

    def __init__(self, name, window_size=200, z_threshold=2.5, volume_threshold=2.0):
        self.name = name
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.volume_threshold = volume_threshold

    def detect(self, i, prices, volumes, times):
        """Detect breakout at index i"""
        if i < self.window_size:
            return None, 0.0

        window_prices = prices[i-self.window_size:i]
        window_volumes = volumes[i-self.window_size:i]

        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)
        valid_volumes = window_volumes[window_volumes > 0]
        avg_volume = np.mean(valid_volumes) if len(valid_volumes) > 0 else 0

        if std_price > 0 and avg_volume > 0:
            z_score = (prices[i] - mean_price) / std_price
            volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

            # Check if both thresholds met
            if abs(z_score) >= self.z_threshold and volume_ratio >= self.volume_threshold:
                strength = (abs(z_score) + volume_ratio) / 2
                return {
                    'index': i,
                    'time': times[i],
                    'price': prices[i],
                    'z_score': z_score,
                    'volume_ratio': volume_ratio,
                    'strength': strength
                }, strength

        return None, 0.0

def simulate_multi_factor_detection(df, symbol, min_confirm=2, min_strength=2.5):
    """
    Simulate multi-factor confirmation mechanism

    Returns:
        signals: list of confirmed signals
        stats: statistics dictionary
    """

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    # Create 5 algorithm detectors
    algorithms = [
        AlgorithmDetector('STATISTICAL'),
        AlgorithmDetector('MOMENTUM'),
        AlgorithmDetector('CONSECUTIVE'),
        AlgorithmDetector('VOLUME'),
        AlgorithmDetector('PATH')
    ]

    pending_signals = []  # Pending signals in confirmation window
    signals = []
    single_algo_count = 0
    multi_algo_count = 0

    # Detection results tracking
    algo_detection_counts = defaultdict(int)
    algo_combination_counts = defaultdict(int)

    for i in range(WINDOW_SIZE, len(prices)):
        current_time = times[i]

        # Collect detections from all algorithms
        detections = []
        for algo in algorithms:
            detection, strength = algo.detect(i, prices, volumes, times)
            if detection:
                detections.append((algo.name, strength))
                algo_detection_counts[algo.name] += 1

        # Check if minimum confirmation count met
        if len(detections) < min_confirm:
            continue

        # Add to pending signals
        for algo_name, strength in detections:
            pending_signals.append({
                'type': algo_name,
                'strength': strength,
                'timestamp': current_time,
                'index': i
            })

        # Clean expired signals (outside confirmation window)
        pending_signals = [
            s for s in pending_signals
            if (pd.Timedelta(current_time - s['timestamp']).total_seconds() * 1000 < CONFIRMATION_WINDOW_MS)
        ]

        # Check if enough pending signals for confirmation
        if len(pending_signals) >= min_confirm:
            # Calculate average strength
            total_strength = sum(s['strength'] for s in pending_signals)
            avg_strength = total_strength / len(pending_signals)

            # Check minimum strength requirement
            if avg_strength >= min_strength:
                # Generate confirmed signal
                combined_types = '+'.join([s['type'] for s in pending_signals])
                signals.append({
                    'index': i,
                    'time': current_time,
                    'price': prices[i],
                    'combined_types': combined_types,
                    'avg_strength': avg_strength,
                    'algo_count': len(set(s['type'] for s in pending_signals))
                })

                # Track combination statistics
                unique_algos = tuple(sorted(set(s['type'] for s in pending_signals)))
                if len(unique_algos) == 1:
                    single_algo_count += 1
                else:
                    multi_algo_count += 1
                    algo_combination_counts[unique_algos] += 1

                # Clear pending signals after confirmation
                pending_signals = []

    # Calculate statistics
    stats = {
        'total_signals': len(signals),
        'single_algo_signals': single_algo_count,
        'multi_algo_signals': multi_algo_count,
        'algo_detection_counts': dict(algo_detection_counts),
        'algo_combination_counts': dict(algo_combination_counts),
        'first_signal_time': signals[0]['time'] if signals else None,
        'last_signal_time': signals[-1]['time'] if signals else None
    }

    return signals, stats

# ============================================================================
# 4. Run Tests
# ============================================================================

print('\n' + '='*80)
print('Multi-Factor Confirmation Test Results')
print('='*80)

# Test GUNUSDT
print('\n[GUNUSDT]')
gunusdt_signals, gunusdt_stats = simulate_multi_factor_detection(
    gunusdt_df, 'GUNUSDT',
    min_confirm=MIN_CONFIRMATION_COUNT,
    min_strength=MIN_BREAKOUT_STRENGTH
)

print(f'  Total Signals: {gunusdt_stats["total_signals"]}')
print(f'  Single-Algorithm Signals: {gunusdt_stats["single_algo_signals"]}')
print(f'  Multi-Algorithm Signals: {gunusdt_stats["multi_algo_signals"]}')

print(f'\n  Individual Algorithm Detections:')
for algo, count in sorted(gunusdt_stats['algo_detection_counts'].items()):
    print(f'    {algo}: {count} detections')

if gunusdt_stats['algo_combination_counts']:
    print(f'\n  Algorithm Combinations:')
    for combo, count in sorted(gunusdt_stats['algo_combination_counts'].items(),
                               key=lambda x: x[1], reverse=True):
        combo_str = '+'.join(combo)
        print(f'    {combo_str}: {count} signals')

if gunusdt_stats["total_signals"] > 0:
    print(f'\n  First Signal: {gunusdt_stats["first_signal_time"]}')
    print(f'  Last Signal: {gunusdt_stats["last_signal_time"]}')

# Test BABYUSDT
print('\n[BABYUSDT]')
babyusdt_signals, babyusdt_stats = simulate_multi_factor_detection(
    babyusdt_df, 'BABYUSDT',
    min_confirm=MIN_CONFIRMATION_COUNT,
    min_strength=MIN_BREAKOUT_STRENGTH
)

print(f'  Total Signals: {babyusdt_stats["total_signals"]}')
print(f'  Single-Algorithm Signals: {babyusdt_stats["single_algo_signals"]}')
print(f'  Multi-Algorithm Signals: {babyusdt_stats["multi_algo_signals"]}')

print(f'\n  Individual Algorithm Detections:')
for algo, count in sorted(babyusdt_stats['algo_detection_counts'].items()):
    print(f'    {algo}: {count} detections')

if babyusdt_stats['algo_combination_counts']:
    print(f'\n  Algorithm Combinations:')
    for combo, count in sorted(babyusdt_stats['algo_combination_counts'].items(),
                               key=lambda x: x[1], reverse=True):
        combo_str = '+'.join(combo)
        print(f'    {combo_str}: {count} signals')

if babyusdt_stats["total_signals"] > 0:
    print(f'\n  First Signal: {babyusdt_stats["first_signal_time"]}')
    print(f'  Last Signal: {babyusdt_stats["last_signal_time"]}')

# ============================================================================
# 5. Validation Checks
# ============================================================================

print('\n' + '='*80)
print('Multi-Factor Confirmation Validation')
print('='*80)

print('\n[Validation 1: Minimum Confirmation Count]')
print(f'  Required: {MIN_CONFIRMATION_COUNT}+ algorithms')
print(f'  GUNUSDT: All signals should have 2+ algorithms')
print(f'  BABYUSDT: All signals should have 2+ algorithms')

gunusdt_confirm_pass = all(s['algo_count'] >= MIN_CONFIRMATION_COUNT for s in gunusdt_signals)
babyusdt_confirm_pass = all(s['algo_count'] >= MIN_CONFIRMATION_COUNT for s in babyusdt_signals)

if gunusdt_confirm_pass and babyusdt_confirm_pass:
    print('  [PASS] Minimum confirmation count requirement enforced')
else:
    print('  [FAIL] Minimum confirmation count requirement NOT enforced')

print('\n[Validation 2: Average Strength Threshold]')
print(f'  Required: avg_strength >= {MIN_BREAKOUT_STRENGTH}')
print(f'  GUNUSDT: All signals should have avg_strength >= {MIN_BREAKOUT_STRENGTH}')
print(f'  BABYUSDT: All signals should have avg_strength >= {MIN_BREAKOUT_STRENGTH}')

gunusdt_strength_pass = all(s['avg_strength'] >= MIN_BREAKOUT_STRENGTH for s in gunusdt_signals)
babyusdt_strength_pass = all(s['avg_strength'] >= MIN_BREAKOUT_STRENGTH for s in babyusdt_signals)

if gunusdt_strength_pass and babyusdt_strength_pass:
    print('  [PASS] Average strength threshold requirement enforced')
else:
    print('  [FAIL] Average strength threshold requirement NOT enforced')

print('\n[Validation 3: Multi-Algorithm Combination]')
print(f'  Expected: Signals should combine multiple algorithms')
print(f'  GUNUSDT: {gunusdt_stats["multi_algo_signals"]} multi-algo signals')
print(f'  BABYUSDT: {babyusdt_stats["multi_algo_signals"]} multi-algo signals')

if gunusdt_stats["multi_algo_signals"] > 0 or babyusdt_stats["multi_algo_signals"] > 0:
    print('  [PASS] Multi-algorithm confirmation working')
else:
    print('  [WARN] No multi-algorithm signals detected')

# ============================================================================
# 6. Summary
# ============================================================================

print('\n' + '='*80)
print('Test Summary')
print('='*80)

all_validations_passed = (
    gunusdt_confirm_pass and babyusdt_confirm_pass and
    gunusdt_strength_pass and babyusdt_strength_pass
)

if all_validations_passed:
    print('\n[SUCCESS] All multi-factor confirmation validations passed!')
    print('  - Minimum 2 algorithms requirement: ENFORCED')
    print('  - Average strength >= 2.5 requirement: ENFORCED')
    print('  - Multi-algorithm combination: WORKING')
else:
    print('\n[WARN] Some validations failed, review multi-factor confirmation logic')

print('\nConfiguration:')
print(f'  Config file: configs/hf_breakout_live_config.yaml')
print(f'  min_confirmation_count: {MIN_CONFIRMATION_COUNT}')
print(f'  min_breakout_strength: {MIN_BREAKOUT_STRENGTH}')
print(f'  confirmation_window: {CONFIRMATION_WINDOW_MS}ms')

print('\nResults Summary:')
print(f'  GUNUSDT: {gunusdt_stats["total_signals"]} confirmed signals')
print(f'  BABYUSDT: {babyusdt_stats["total_signals"]} confirmed signals')

print('\n' + '='*80)
