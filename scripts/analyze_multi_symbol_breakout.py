"""
Multi-Symbol Breakout Analysis - Compare GUNUSDT and BABYUSDT
Analyze different symbols to find universal breakout patterns
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

print('='*80)
print('MULTI-SYMBOL BREAKOUT ANALYSIS')
print('='*80)

# ============================================================================
# 1. Load Data for Both Symbols
# ============================================================================

print('\n[LOADING DATA]')

# GUNUSDT data (2 hours)
gunusdt_files = [
    Path('data/tick/binance/GUNUSDT_2026010715.parquet'),
    Path('data/tick/binance/GUNUSDT_2026010716.parquet')
]

# BABYUSDT data (4 hours)
babyusdt_files = [
    Path('data/tick/binance/BABYUSDT_2026010720.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010721.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010722.parquet'),
    Path('data/tick/binance/BABYUSDT_2026010723.parquet')
]

# Load GUNUSDT
gunusdt_dfs = []
for f in gunusdt_files:
    if f.exists():
        df = pd.read_parquet(f)
        gunusdt_dfs.append(df)
        print(f'  Loaded {f.name}: {len(df)} rows')

if gunusdt_dfs:
    gunusdt_df = pd.concat(gunusdt_dfs, ignore_index=True)
    gunusdt_df['event_time_pd'] = pd.to_datetime(gunusdt_df['event_time'])
    gunusdt_df = gunusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    gunusdt_df['volume_increment'] = gunusdt_df['volume'].diff().fillna(0)
    print(f'  GUNUSDT combined: {len(gunusdt_df)} rows')
    print(f'  Time range: {gunusdt_df["event_time_pd"].min()} to {gunusdt_df["event_time_pd"].max()}')

# Load BABYUSDT
babyusdt_dfs = []
for f in babyusdt_files:
    if f.exists():
        df = pd.read_parquet(f)
        babyusdt_dfs.append(df)
        print(f'  Loaded {f.name}: {len(df)} rows')

if babyusdt_dfs:
    babyusdt_df = pd.concat(babyusdt_dfs, ignore_index=True)
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df = babyusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    babyusdt_df['volume_increment'] = babyusdt_df['volume'].diff().fillna(0)
    print(f'  BABYUSDT combined: {len(babyusdt_df)} rows')
    print(f'  Time range: {babyusdt_df["event_time_pd"].min()} to {babyusdt_df["event_time_pd"].max()}')

# ============================================================================
# 2. Price Statistics Comparison
# ============================================================================

print('\n' + '='*80)
print('PRICE STATISTICS COMPARISON')
print('='*80)

def analyze_price_movement(df, symbol):
    prices = df['price'].values
    open_price = prices[0]
    close_price = prices[-1]
    high_price = np.max(prices)
    low_price = np.min(prices)
    total_change = (close_price - open_price) / open_price * 100

    print(f'\n{symbol}:')
    print(f'  Open:  {open_price:.8f}')
    print(f'  Close: {close_price:.8f}')
    print(f'  High:  {high_price:.8f}')
    print(f'  Low:   {low_price:.8f}')
    print(f'  Total Change: {total_change:+.2f}%')
    print(f'  Range: {high_price - low_price:.8f}')

    return {
        'symbol': symbol,
        'open': open_price,
        'close': close_price,
        'high': high_price,
        'low': low_price,
        'total_change': total_change,
        'range': high_price - low_price
    }

gunusdt_stats = analyze_price_movement(gunusdt_df, 'GUNUSDT')
babyusdt_stats = analyze_price_movement(babyusdt_df, 'BABYUSDT')

# ============================================================================
# 3. Breakout Detection with Different Thresholds
# ============================================================================

print('\n' + '='*80)
print('BREAKOUT DETECTION WITH DIFFERENT THRESHOLDS')
print('='*80)

def detect_breakouts(df, symbol, window_size=200):
    """Detect breakouts with multiple Z-Score thresholds"""
    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    results = {}

    for threshold in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        breakouts = []

        for i in range(window_size, len(prices)):
            window_prices = prices[i-window_size:i]
            window_volumes = volumes[i-window_size:i]

            mean_price = np.mean(window_prices)
            std_price = np.std(window_prices)
            avg_volume = np.mean(window_volumes[window_volumes > 0]) if np.any(window_volumes > 0) else 0

            if std_price > 0 and avg_volume > 0:
                z_score = (prices[i] - mean_price) / std_price
                volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

                # Multi-factor signal
                if abs(z_score) >= threshold and volume_ratio >= 1.5:
                    potential_profit = (prices[-1] - prices[i]) / prices[i] * 100
                    breakouts.append({
                        'index': i,
                        'time': times[i],
                        'price': prices[i],
                        'z_score': z_score,
                        'volume_ratio': volume_ratio,
                        'potential_profit': potential_profit
                    })

        results[threshold] = breakouts

    return results

print('\n[GUNUSDT Breakout Analysis]')
gunusdt_breakouts = detect_breakouts(gunusdt_df, 'GUNUSDT')
for threshold, signals in gunusdt_breakouts.items():
    if signals:
        first = signals[0]
        print(f'  Z>={threshold}: {len(signals):3d} signals, First at {pd.to_datetime(first["time"]).strftime("%H:%M:%S")}, Profit: {first["potential_profit"]:.2f}%')

print('\n[BABYUSDT Breakout Analysis]')
babyusdt_breakouts = detect_breakouts(babyusdt_df, 'BABYUSDT')
for threshold, signals in babyusdt_breakouts.items():
    if signals:
        first = signals[0]
        print(f'  Z>={threshold}: {len(signals):3d} signals, First at {pd.to_datetime(first["time"]).strftime("%H:%M:%S")}, Profit: {first["potential_profit"]:.2f}%')

# ============================================================================
# 4. Signal Clustering Analysis
# ============================================================================

print('\n' + '='*80)
print('SIGNAL CLUSTERING ANALYSIS')
print('='*80)

def analyze_signal_clustering(df, symbol, window_size=200):
    """Analyze signal clustering patterns"""
    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    # Detect all signals with Z >= 1.5
    signals = []
    for i in range(window_size, len(prices)):
        window_prices = prices[i-window_size:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)

        if std_price > 0:
            z_score = (prices[i] - mean_price) / std_price
            if abs(z_score) >= 1.5:
                signals.append({
                    'index': i,
                    'time': times[i],
                    'z_score': z_score
                })

    # Group by minute
    signals_df = pd.DataFrame(signals)
    if len(signals_df) > 0:
        signals_df['minute'] = signals_df['time'].dt.floor('1min')
        signal_counts = signals_df.groupby('minute').size()

        # Find clusters (3+ signals per minute)
        clusters = signal_counts[signal_counts >= 3].sort_values(ascending=False)

        print(f'\n{symbol}:')
        print(f'  Total signals: {len(signals)}')
        print(f'  Minutes with clusters: {len(clusters)}')

        if len(clusters) > 0:
            print(f'  Top 5 cluster minutes:')
            for minute, count in clusters.head(5).items():
                minute_str = minute.strftime('%H:%M')
                print(f'    {minute_str}: {count} signals')

            return {
                'total_signals': len(signals),
                'cluster_minutes': len(clusters),
                'max_cluster_size': clusters.max(),
                'clusters': clusters
            }

    return None

gunusdt_clusters = analyze_signal_clustering(gunusdt_df, 'GUNUSDT')
babyusdt_clusters = analyze_signal_clustering(babyusdt_df, 'BABYUSDT')

# ============================================================================
# 5. Volume Surge Analysis
# ============================================================================

print('\n' + '='*80)
print('VOLUME SURGE ANALYSIS')
print('='*80)

def analyze_volume_surges(df, symbol):
    """Analyze volume surge patterns"""
    df['minute'] = df['event_time_pd'].dt.floor('1min')

    minute_stats = df.groupby('minute').agg({
        'price': ['first', 'last'],
        'volume_increment': 'sum'
    }).reset_index()

    minute_stats.columns = ['minute', 'price_first', 'price_last', 'volume_total']
    minute_stats['price_change_pct'] = ((minute_stats['price_last'] - minute_stats['price_first']) /
                                        minute_stats['price_first'] * 100)

    # Calculate average volume
    avg_volume = minute_stats['volume_total'].mean()

    # Find volume surges (2x+ average)
    surges = minute_stats[minute_stats['volume_total'] >= avg_volume * 2].copy()

    print(f'\n{symbol}:')
    print(f'  Average volume per minute: {avg_volume:,.0f}')
    print(f'  Volume surges detected: {len(surges)}')

    if len(surges) > 0:
        surges = surges.sort_values('volume_total', ascending=False)
        print(f'  Top 5 volume surges:')
        for _, row in surges.head(5).iterrows():
            minute_str = row['minute'].strftime('%H:%M')
            vol_ratio = row['volume_total'] / avg_volume
            print(f'    {minute_str}: {row["volume_total"]:,.0f} ({vol_ratio:.1f}x avg), Price: {row["price_change_pct"]:+.2f}%')

        return {
            'avg_volume': avg_volume,
            'surge_count': len(surges),
            'max_surge': surges.iloc[0]['volume_total'],
            'max_surge_ratio': surges.iloc[0]['volume_total'] / avg_volume
        }

    return None

gunusdt_volume = analyze_volume_surges(gunusdt_df, 'GUNUSDT')
babyusdt_volume = analyze_volume_surges(babyusdt_df, 'BABYUSDT')

# ============================================================================
# 6. Optimal Entry Point Analysis
# ============================================================================

print('\n' + '='*80)
print('OPTIMAL ENTRY POINT ANALYSIS')
print('='*80)

def find_optimal_entries(breakouts_dict, symbol):
    """Find optimal entry points with different risk profiles"""
    if not breakouts_dict or 2.5 not in breakouts_dict:
        return None

    signals = breakouts_dict[2.5]
    if not signals:
        return None

    # Sort by time
    signals_sorted = sorted(signals, key=lambda x: x['index'])

    # Aggressive (first signal)
    aggressive = signals_sorted[0]

    # Best profit
    best_profit = max(signals, key=lambda x: x['potential_profit'])

    # Balance of early and good profit (first with profit > 5%)
    balanced = None
    for sig in signals_sorted:
        if sig['potential_profit'] >= 5.0:
            balanced = sig
            break

    if not balanced:
        balanced = aggressive

    print(f'\n{symbol}:')
    print(f'  Aggressive Entry:')
    print(f'    Time: {pd.to_datetime(aggressive["time"])}')
    print(f'    Price: {aggressive["price"]:.8f}')
    print(f'    Z-Score: {aggressive["z_score"]:.2f}')
    print(f'    Volume Ratio: {aggressive["volume_ratio"]:.2f}x')
    print(f'    Profit: {aggressive["potential_profit"]:.2f}%')

    if balanced != aggressive:
        print(f'  Balanced Entry:')
        print(f'    Time: {pd.to_datetime(balanced["time"])}')
        print(f'    Price: {balanced["price"]:.8f}')
        print(f'    Z-Score: {balanced["z_score"]:.2f}')
        print(f'    Volume Ratio: {balanced["volume_ratio"]:.2f}x')
        print(f'    Profit: {balanced["potential_profit"]:.2f}%')

    print(f'  Best Profit Entry:')
    print(f'    Time: {pd.to_datetime(best_profit["time"])}')
    print(f'    Price: {best_profit["price"]:.8f}')
    print(f'    Z-Score: {best_profit["z_score"]:.2f}')
    print(f'    Volume Ratio: {best_profit["volume_ratio"]:.2f}x')
    print(f'    Profit: {best_profit["potential_profit"]:.2f}%')

    return {
        'aggressive': aggressive,
        'balanced': balanced,
        'best_profit': best_profit
    }

gunusdt_entries = find_optimal_entries(gunusdt_breakouts, 'GUNUSDT')
babyusdt_entries = find_optimal_entries(babyusdt_breakouts, 'BABYUSDT')

# ============================================================================
# 7. Universal Pattern Discovery
# ============================================================================

print('\n' + '='*80)
print('UNIVERSAL PATTERN DISCOVERY')
print('='*80)

print('\n[COMMON PATTERNS ACROSS SYMBOLS]')

# Pattern 1: Signal clustering before breakout
print('\n1. SIGNAL CLUSTERING BEFORE BREAKOUT:')
if gunusdt_clusters and babyusdt_clusters:
    print(f'  GUNUSDT: {gunusdt_clusters["max_cluster_size"]} signals in peak minute')
    print(f'  BABYUSDT: {babyusdt_clusters["max_cluster_size"]} signals in peak minute')

    if (gunusdt_clusters['max_cluster_size'] >= 30 and
        babyusdt_clusters['max_cluster_size'] >= 30):
        print(f'  CONCLUSION: Both show signal clustering >= 30/min')
        print(f'  RECOMMENDATION: Use clustering >= 30/min as early warning')

# Pattern 2: Volume surge confirmation
print('\n2. VOLUME SURGE CONFIRMATION:')
if gunusdt_volume and babyusdt_volume:
    print(f'  GUNUSDT: Max surge {gunusdt_volume["max_surge_ratio"]:.1f}x average')
    print(f'  BABYUSDT: Max surge {babyusdt_volume["max_surge_ratio"]:.1f}x average')

    if (gunusdt_volume['max_surge_ratio'] >= 5.0 and
        babyusdt_volume['max_surge_ratio'] >= 5.0):
        print(f'  CONCLUSION: Both show volume surges >= 5x average')
        print(f'  RECOMMENDATION: Use volume surge >= 5x as confirmation')

# Pattern 3: Z-Score threshold for entry
print('\n3. Z-SCORE THRESHOLD FOR ENTRY:')
print(f'  Testing thresholds: 1.5, 2.0, 2.5, 3.0, 4.0, 5.0')

for threshold in [2.0, 2.5, 3.0]:
    gun_count = len(gunusdt_breakouts.get(threshold, []))
    baby_count = len(babyusdt_breakouts.get(threshold, []))
    print(f'  Z>={threshold}: GUNUSDT={gun_count}, BABYUSDT={baby_count}')

    if gun_count > 0 and baby_count > 0:
        if gun_count <= 100 and baby_count <= 100:
            print(f'    Both symbols have manageable signal count')
            if threshold == 2.5:
                print(f'    RECOMMENDATION: Z-Score >= 2.5 is optimal threshold')

# Pattern 4: Volume ratio confirmation
print('\n4. VOLUME RATIO CONFIRMATION:')
print(f'  Using volume ratio >= 1.5x as filter')

# Calculate average volume ratio for signals
def get_avg_volume_ratio(breakouts):
    if not breakouts or 2.5 not in breakouts:
        return None
    signals = breakouts[2.5]
    if not signals:
        return None
    ratios = [s['volume_ratio'] for s in signals]
    return np.mean(ratios), np.median(ratios), np.min(ratios), np.max(ratios)

gun_vol_stats = get_avg_volume_ratio(gunusdt_breakouts)
baby_vol_stats = get_avg_volume_ratio(babyusdt_breakouts)

if gun_vol_stats and baby_vol_stats:
    print(f'  GUNUSDT: Mean={gun_vol_stats[0]:.2f}x, Median={gun_vol_stats[1]:.2f}x')
    print(f'  BABYUSDT: Mean={baby_vol_stats[0]:.2f}x, Median={baby_vol_stats[1]:.2f}x')

    if (gun_vol_stats[1] >= 2.0 and baby_vol_stats[1] >= 2.0):
        print(f'  CONCLUSION: Both show median volume ratio >= 2.0x')
        print(f'  RECOMMENDATION: Volume ratio >= 2.0x is good confirmation')

# ============================================================================
# 8. Universal Strategy Recommendations
# ============================================================================

print('\n' + '='*80)
print('UNIVERSAL STRATEGY RECOMMENDATIONS')
print('='*80)

print('\n[PHASE 1: PRE-WARNING]')
print('  Signal Clustering Detection:')
print('    - Threshold: 30+ signals per minute')
print('    - Window: 1 minute')
print('    - Action: Prepare for potential breakout')

print('\n[PHASE 2: BREAKOUT DETECTION]')
print('  Statistical Breakout:')
print('    - Z-Score threshold: 2.5')
print('    - Window size: 200 ticks')
print('    - Action: Monitor closely')

print('\n[PHASE 3: CONFIRMATION]')
print('  Multi-Factor Confirmation:')
print('    - Z-Score >= 2.5')
print('    - Volume Ratio >= 2.0x')
print('    - Price Change >= 0.5%')
print('    - Action: Enter position')

print('\n[PHASE 4: ENTRY STRATEGY]')
print('  Aggressive Entry:')
print('    - First strong signal (Z >= 2.5, Vol >= 2.0x)')
print('    - Position: 30-40%')
print('    - Higher profit potential, higher risk')

print('\n  Balanced Entry:')
print('    - First signal with 5%+ profit potential')
print('    - Position: 40-50%')
print('    - Good balance of risk and reward')

print('\n  Conservative Entry:')
print('    - Volume surge confirmation (5x+)')
print('    - Position: 20-30%')
print('    - Lower risk, confirmed trend')

print('\n[RISK MANAGEMENT]')
print('  Stop Loss: 2-3% below entry')
print('  Take Profit: 5-8% from entry')
print('  Trail Stop: 2% after 5% profit')
print('  Max Position: 50% per trade')

print('\n' + '='*80)
print('Analysis Complete')
print('='*80)
