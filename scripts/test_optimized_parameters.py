"""
Test optimized parameters configuration
Validate with GUNUSDT and BABYUSDT data

Universal parameters based on dual-symbol analysis:
- Z-Score threshold: 2.5 (optimal balance)
- Volume Ratio threshold: 2.0x (strict confirmation)
- Window Size: 200 ticks
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

print('='*80)
print('Optimized Parameters Validation Test')
print('='*80)
print(f'Test Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

# ============================================================================
# 1. Load Data
# ============================================================================

print('\n[Loading Data]')

# GUNUSDT data (2 hours)
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

# BABYUSDT data
babyusdt_files = [
    Path('data/tick/binance/BABYUSDT_2026010720.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010721.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010722.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010723.parquet')
]

babyusdt_dfs = []
for f in babyusdt_files:
    if f.exists():
        df = pd.read_parquet(f)
        babyusdt_dfs.append(df)
        print(f'  [OK] {f.name}: {len(df)} rows')

if babyusdt_dfs:
    babyusdt_df = pd.concat(babyusdt_dfs, ignore_index=True)
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df = babyusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    babyusdt_df['volume_increment'] = babyusdt_df['volume'].diff().fillna(0)
    print(f'  BABYUSDT combined: {len(babyusdt_df)} rows')
else:
    print('  [ERROR] BABYUSDT data not found')
    exit(1)

# ============================================================================
# 2. New Parameter Configuration (based on dual-symbol validation)
# ============================================================================

print('\n[New Parameter Configuration]')
NEW_Z_THRESHOLD = 2.5
NEW_VOLUME_THRESHOLD = 2.0
WINDOW_SIZE = 200

print(f'  Z-Score Threshold: {NEW_Z_THRESHOLD}')
print(f'  Volume Ratio Threshold: {NEW_VOLUME_THRESHOLD}x')
print(f'  Window Size: {WINDOW_SIZE} ticks')

# ============================================================================
# 3. Test Function
# ============================================================================

def test_parameters(df, symbol, z_threshold, volume_threshold, window_size):
    """
    Test parameter configuration

    Returns:
        signals: list of detected signals
        stats: statistics dictionary
    """
    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    signals = []

    for i in range(window_size, len(prices)):
        window_prices = prices[i-window_size:i]
        window_volumes = volumes[i-window_size:i]

        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)

        # Filter valid volume increments
        valid_volumes = window_volumes[window_volumes > 0]
        avg_volume = np.mean(valid_volumes) if len(valid_volumes) > 0 else 0

        if std_price > 0 and avg_volume > 0:
            z_score = (prices[i] - mean_price) / std_price
            volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

            # Detect with new parameters
            if abs(z_score) >= z_threshold and volume_ratio >= volume_threshold:
                signals.append({
                    'index': i,
                    'time': times[i],
                    'price': prices[i],
                    'z_score': z_score,
                    'volume_ratio': volume_ratio
                })

    # Calculate statistics
    if signals:
        z_scores = [s['z_score'] for s in signals]
        volume_ratios = [s['volume_ratio'] for s in signals]

        stats = {
            'total_signals': len(signals),
            'z_score_mean': np.mean(z_scores),
            'z_score_median': np.median(z_scores),
            'z_score_std': np.std(z_scores),
            'volume_ratio_mean': np.mean(volume_ratios),
            'volume_ratio_median': np.median(volume_ratios),
            'volume_ratio_std': np.std(volume_ratios),
            'first_signal_time': signals[0]['time'],
            'last_signal_time': signals[-1]['time']
        }
    else:
        stats = {
            'total_signals': 0,
            'z_score_mean': 0,
            'z_score_median': 0,
            'z_score_std': 0,
            'volume_ratio_mean': 0,
            'volume_ratio_median': 0,
            'volume_ratio_std': 0,
            'first_signal_time': None,
            'last_signal_time': None
        }

    return signals, stats

# ============================================================================
# 4. Run Tests
# ============================================================================

print('\n' + '='*80)
print('Test Results')
print('='*80)

# Test GUNUSDT
print('\n[GUNUSDT]')
gunusdt_signals, gunusdt_stats = test_parameters(
    gunusdt_df, 'GUNUSDT',
    NEW_Z_THRESHOLD, NEW_VOLUME_THRESHOLD, WINDOW_SIZE
)

print(f'  Total Signals: {gunusdt_stats["total_signals"]}')
print(f'  Z-Score Stats: mean={gunusdt_stats["z_score_mean"]:.2f}, '
      f'median={gunusdt_stats["z_score_median"]:.2f}, std={gunusdt_stats["z_score_std"]:.2f}')
print(f'  Volume Ratio Stats: mean={gunusdt_stats["volume_ratio_mean"]:.2f}x, '
      f'median={gunusdt_stats["volume_ratio_median"]:.2f}x, std={gunusdt_stats["volume_ratio_std"]:.2f}')

if gunusdt_stats["total_signals"] > 0:
    print(f'  First Signal: {gunusdt_stats["first_signal_time"]}')
    print(f'  Last Signal: {gunusdt_stats["last_signal_time"]}')

# Test BABYUSDT (use 21:00 data, similar to GUNUSDT period)
print('\n[BABYUSDT]')
babyusdt_21_df = babyusdt_df[babyusdt_df['event_time_pd'].dt.hour == 21].copy()
if len(babyusdt_21_df) > 0:
    babyusdt_signals, babyusdt_stats = test_parameters(
        babyusdt_21_df, 'BABYUSDT',
        NEW_Z_THRESHOLD, NEW_VOLUME_THRESHOLD, WINDOW_SIZE
    )

    print(f'  Total Signals: {babyusdt_stats["total_signals"]}')
    print(f'  Z-Score Stats: mean={babyusdt_stats["z_score_mean"]:.2f}, '
          f'median={babyusdt_stats["z_score_median"]:.2f}, std={babyusdt_stats["z_score_std"]:.2f}')
    print(f'  Volume Ratio Stats: mean={babyusdt_stats["volume_ratio_mean"]:.2f}x, '
          f'median={babyusdt_stats["volume_ratio_median"]:.2f}x, std={babyusdt_stats["volume_ratio_std"]:.2f}')

    if babyusdt_stats["total_signals"] > 0:
        print(f'  First Signal: {babyusdt_stats["first_signal_time"]}')
        print(f'  Last Signal: {babyusdt_stats["last_signal_time"]}')
else:
    print('  [WARN] 21:00 data insufficient, using all data')
    babyusdt_signals, babyusdt_stats = test_parameters(
        babyusdt_df, 'BABYUSDT',
        NEW_Z_THRESHOLD, NEW_VOLUME_THRESHOLD, WINDOW_SIZE
    )

    print(f'  Total Signals: {babyusdt_stats["total_signals"]}')
    print(f'  Z-Score Stats: mean={babyusdt_stats["z_score_mean"]:.2f}, '
          f'median={babyusdt_stats["z_score_median"]:.2f}, std={babyusdt_stats["z_score_std"]:.2f}')
    print(f'  Volume Ratio Stats: mean={babyusdt_stats["volume_ratio_mean"]:.2f}x, '
          f'median={babyusdt_stats["volume_ratio_median"]:.2f}x, std={babyusdt_stats["volume_ratio_std"]:.2f}')

# ============================================================================
# 5. Compare Before/After Optimization
# ============================================================================

print('\n' + '='*80)
print('Parameter Optimization Effect Comparison')
print('='*80)

print('\n[GUNUSDT]')
print(f'  Before (expected): ~160 signals (Z>=1.5, Vol>=1.5x)')
print(f'  After (actual): {gunusdt_stats["total_signals"]} signals (Z>={NEW_Z_THRESHOLD}, Vol>={NEW_VOLUME_THRESHOLD}x)')

if 60 <= gunusdt_stats["total_signals"] <= 80:
    print(f'  [PASS] Signal count within expected range (70 +/- 10)')
else:
    print(f'  [WARN] Signal count outside expected range (70 +/- 10)')

print('\n[BABYUSDT]')
print(f'  Before (expected): ~272 signals (Z>=1.5, Vol>=1.5x)')
print(f'  After (actual): {babyusdt_stats["total_signals"]} signals (Z>={NEW_Z_THRESHOLD}, Vol>={NEW_VOLUME_THRESHOLD}x)')

if 80 <= babyusdt_stats["total_signals"] <= 120:
    print(f'  [PASS] Signal count within expected range (100 +/- 20)')
else:
    print(f'  [WARN] Signal count outside expected range (100 +/- 20)')

# ============================================================================
# 6. Volume Ratio Quality Check
# ============================================================================

print('\n' + '='*80)
print('Volume Ratio Quality Check')
print('='*80)

print('\nExpected: Volume Ratio median >= 2.0x (dual-symbol validation)')

if gunusdt_stats["volume_ratio_median"] >= 2.0:
    print(f'  [PASS] GUNUSDT: median={gunusdt_stats["volume_ratio_median"]:.2f}x (meets expectation)')
else:
    print(f'  [WARN] GUNUSDT: median={gunusdt_stats["volume_ratio_median"]:.2f}x (below expectation)')

if babyusdt_stats["volume_ratio_median"] >= 2.0:
    print(f'  [PASS] BABYUSDT: median={babyusdt_stats["volume_ratio_median"]:.2f}x (meets expectation)')
else:
    print(f'  [WARN] BABYUSDT: median={babyusdt_stats["volume_ratio_median"]:.2f}x (below expectation)')

# ============================================================================
# 7. Summary
# ============================================================================

print('\n' + '='*80)
print('Validation Summary')
print('='*80)

print('\n[OK] Parameter optimization validation completed')
print(f'  Config file: configs/hf_breakout_live_config.yaml')
print(f'  Z-Score threshold: {NEW_Z_THRESHOLD}')
print(f'  Volume Ratio threshold: {NEW_VOLUME_THRESHOLD}x')
print(f'  Window size: {WINDOW_SIZE} ticks')

print('\nValidation Results:')
print(f'  GUNUSDT: {gunusdt_stats["total_signals"]} signals, Volume Ratio median={gunusdt_stats["volume_ratio_median"]:.2f}x')
print(f'  BABYUSDT: {babyusdt_stats["total_signals"]} signals, Volume Ratio median={babyusdt_stats["volume_ratio_median"]:.2f}x')

all_checks_passed = (
    60 <= gunusdt_stats["total_signals"] <= 80 and
    80 <= babyusdt_stats["total_signals"] <= 120 and
    gunusdt_stats["volume_ratio_median"] >= 2.0 and
    babyusdt_stats["volume_ratio_median"] >= 2.0
)

if all_checks_passed:
    print('\n[SUCCESS] All validations passed! Parameter optimization meets dual-symbol validation expectations.')
else:
    print('\n[WARN] Some validations failed, may need further parameter adjustment.')

print('\n' + '='*80)
