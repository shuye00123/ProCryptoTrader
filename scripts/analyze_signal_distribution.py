"""
Analyze Signal Distribution and Patterns
Understand how 56 signals are distributed over time
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

print('='*80)
print('Signal Distribution Analysis')
print('='*80)

# ============================================================================
# 1. Load Data
# ============================================================================

print('\n[Loading Data]')

gunusdt_files = [
    Path('data/tick/binance/GUNUSDT_2026010715.parquet'),
    Path('data/tick/binance/GUNUSDT_2026010716.parquet')
]

gunusdt_dfs = []
for f in gunusdt_files:
    if f.exists():
        df = pd.read_parquet(f)
        gunusdt_dfs.append(df)

if gunusdt_dfs:
    gunusdt_df = pd.concat(gunusdt_dfs, ignore_index=True)
    gunusdt_df['event_time_pd'] = pd.to_datetime(gunusdt_df['event_time'])
    gunusdt_df = gunusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    gunusdt_df['volume_increment'] = gunusdt_df['volume'].diff().fillna(0)
    print(f'  GUNUSDT: {len(gunusdt_df)} rows')
    print(f'  Time range: {gunusdt_df["event_time_pd"].min()} to {gunusdt_df["event_time_pd"].max()}')

# ============================================================================
# 2. Simulate Signal Generation with Timing Info
# ============================================================================

print('\n[Signal Generation Simulation]')

MIN_CONFIRMATION_COUNT = 2
MIN_BREAKOUT_STRENGTH = 2.5
WINDOW_SIZE = 200
CONFIRMATION_WINDOW_MS = 5000

class AlgorithmDetector:
    def __init__(self, name, window_size=200, z_threshold=2.5, volume_threshold=2.0):
        self.name = name
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.volume_threshold = volume_threshold

    def detect(self, i, prices, volumes, times):
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

def generate_signals_with_timing(df):
    """Generate signals and record detailed timing information"""

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    algorithms = [
        AlgorithmDetector('STATISTICAL'),
        AlgorithmDetector('MOMENTUM'),
        AlgorithmDetector('CONSECUTIVE'),
        AlgorithmDetector('VOLUME'),
        AlgorithmDetector('PATH')
    ]

    pending_signals = []
    signals = []

    for i in range(WINDOW_SIZE, len(prices)):
        current_time = times[i]

        # Collect detections
        detections = []
        for algo in algorithms:
            detection, strength = algo.detect(i, prices, volumes, times)
            if detection:
                detections.append((algo.name, strength))

        # Check minimum confirmation
        if len(detections) < MIN_CONFIRMATION_COUNT:
            continue

        # Add to pending
        for algo_name, strength in detections:
            pending_signals.append({
                'type': algo_name,
                'strength': strength,
                'timestamp': current_time,
                'index': i
            })

        # Clean expired
        pending_signals = [
            s for s in pending_signals
            if pd.Timedelta(current_time - s['timestamp']).total_seconds() * 1000 < CONFIRMATION_WINDOW_MS
        ]

        # Check confirmation
        if len(pending_signals) >= MIN_CONFIRMATION_COUNT:
            total_strength = sum(s['strength'] for s in pending_signals)
            avg_strength = total_strength / len(pending_signals)

            if avg_strength >= MIN_BREAKOUT_STRENGTH:
                combined_types = '+'.join([s['type'] for s in pending_signals])

                signals.append({
                    'index': i,
                    'time': current_time,
                    'price': prices[i],
                    'combined_types': combined_types,
                    'avg_strength': avg_strength,
                    'algo_count': len(set(s['type'] for s in pending_signals))
                })

                pending_signals = []

    return signals

# Generate signals
signals = generate_signals_with_timing(gunusdt_df)

print(f'  Total signals generated: {len(signals)}')

# ============================================================================
# 3. Analyze Signal Distribution
# ============================================================================

print('\n' + '='*80)
print('Signal Time Distribution Analysis')
print('='*80)

if signals:
    # Convert to DataFrame for easier analysis
    signals_df = pd.DataFrame(signals)

    # Calculate time differences
    signals_df['time_diff_seconds'] = signals_df['time'].diff().dt.total_seconds()

    print(f'\n[Time Statistics]')
    print(f'  First signal: {signals_df["time"].iloc[0]}')
    print(f'  Last signal: {signals_df["time"].iloc[-1]}')
    print(f'  Total duration: {signals_df["time"].iloc[-1] - signals_df["time"].iloc[0]}')
    print(f'  Average interval: {signals_df["time_diff_seconds"].mean():.2f} seconds')
    print(f'  Median interval: {signals_df["time_diff_seconds"].median():.2f} seconds')
    print(f'  Min interval: {signals_df["time_diff_seconds"].min():.2f} seconds')
    print(f'  Max interval: {signals_df["time_diff_seconds"].max():.2f} seconds')

    # Interval distribution
    print(f'\n[Interval Distribution]')
    interval_bins = [0, 10, 30, 60, 120, 300, float('inf')]
    interval_labels = ['0-10s', '10-30s', '30-60s', '1-2m', '2-5m', '>5m']

    signals_df['interval_category'] = pd.cut(
        signals_df['time_diff_seconds'],
        bins=interval_bins,
        labels=interval_labels
    )

    interval_dist = signals_df['interval_category'].value_counts().sort_index()
    for category, count in interval_dist.items():
        percentage = count / len(signals_df) * 100
        print(f'  {category}: {count} signals ({percentage:.1f}%)')

    # Per-minute signal density
    print(f'\n[Signal Density per Minute]')
    signals_df['minute'] = signals_df['time'].dt.floor('1min')
    signals_per_minute = signals_df.groupby('minute').size()

    print(f'  Average signals per minute: {signals_per_minute.mean():.2f}')
    print(f'  Max signals in a minute: {signals_per_minute.max()}')
    print(f'  Minutes with signals: {len(signals_per_minute)}')

    # Top 5 busiest minutes
    print(f'\n  Top 5 Busiest Minutes:')
    for minute, count in signals_per_minute.nlargest(5).items():
        minute_str = minute.strftime('%H:%M')
        print(f'    {minute_str}: {count} signals')

    # Signal quality distribution
    print(f'\n[Signal Quality Distribution]')
    print(f'  Average strength: {signals_df["avg_strength"].mean():.2f}')
    print(f'  Median strength: {signals_df["avg_strength"].median():.2f}')
    print(f'  Min strength: {signals_df["avg_strength"].min():.2f}')
    print(f'  Max strength: {signals_df["avg_strength"].max():.2f}')

    # Strength quartiles
    print(f'\n  Strength Quartiles:')
    for q in [0.25, 0.5, 0.75, 0.9, 0.95]:
        value = signals_df['avg_strength'].quantile(q)
        count = (signals_df['avg_strength'] >= value).sum()
        print(f'    {q*100:.0f}th percentile: {value:.2f} ({count} signals above)')

# ============================================================================
# 4. Identify Signal Clusters
# ============================================================================

print('\n' + '='*80)
print('Signal Clustering Analysis')
print('='*80)

# Define a cluster as signals within 60 seconds
CLUSTER_WINDOW_SECONDS = 60

if signals:
    signals_df = pd.DataFrame(signals)
    signals_df = signals_df.sort_values('time').reset_index(drop=True)

    # Identify clusters
    clusters = []
    current_cluster = [signals_df.iloc[0]]

    for idx in range(1, len(signals_df)):
        time_diff = (signals_df.iloc[idx]['time'] - signals_df.iloc[idx-1]['time']).total_seconds()

        if time_diff <= CLUSTER_WINDOW_SECONDS:
            current_cluster.append(signals_df.iloc[idx])
        else:
            clusters.append(current_cluster)
            current_cluster = [signals_df.iloc[idx]]

    if current_cluster:
        clusters.append(current_cluster)

    print(f'\n[Cluster Statistics]')
    print(f'  Total clusters: {len(clusters)}')
    print(f'  Cluster window: {CLUSTER_WINDOW_SECONDS} seconds')
    print(f'  Average cluster size: {np.mean([len(c) for c in clusters]):.1f} signals')
    print(f'  Max cluster size: {max([len(c) for c in clusters])} signals')
    print(f'  Min cluster size: {min([len(c) for c in clusters])} signals')

    # Show top clusters
    print(f'\n[Top 5 Largest Clusters]')
    sorted_clusters = sorted(clusters, key=len, reverse=True)[:5]

    for i, cluster in enumerate(sorted_clusters, 1):
        cluster_df = pd.DataFrame(cluster)
        start_time = cluster_df['time'].min()
        end_time = cluster_df['time'].max()
        duration = (end_time - start_time).total_seconds()
        avg_strength = cluster_df['avg_strength'].mean()
        max_strength = cluster_df['avg_strength'].max()

        print(f'\n  Cluster {i}:')
        print(f'    Size: {len(cluster)} signals')
        print(f'    Time: {start_time.strftime("%H:%M:%S")} - {end_time.strftime("%H:%M:%S")}')
        print(f'    Duration: {duration:.0f} seconds')
        print(f'    Avg strength: {avg_strength:.2f}')
        print(f'    Max strength: {max_strength:.2f}')

        # Price movement during cluster
        start_price = cluster_df['price'].iloc[0]
        end_price = cluster_df['price'].iloc[-1]
        price_change = (end_price - start_price) / start_price * 100
        print(f'    Price change: {price_change:+.2f}%')

# ============================================================================
# 5. Signal Filtering Strategies
# ============================================================================

print('\n' + '='*80)
print('Proposed Signal Filtering Strategies')
print('='*80)

print('\n[Strategy 1: Time-Based Cooldown]')
print('  Only keep first signal in each time window')
print(f'  Config: signal_cooldown_seconds = 30 (default in config)')
print('  Expected: 56 signals -> ~15-20 signals')
print('  Pros: Simple, reduces frequency')
print('  Cons: May miss better signals later')

print('\n[Strategy 2: Quality-Based Selection]')
print('  Only keep signals with strength above threshold')
print('  Config: min_signal_strength = 3.0 (or 90th percentile)')
print('  Expected: 56 signals -> ~5-10 highest quality signals')
print('  Pros: Ensures high-quality entries')
print('  Cons: May miss moderate but good opportunities')

print('\n[Strategy 3: Cluster-Based Selection]')
print('  Within each cluster, select the best signal')
print('  Selection criteria: highest strength, or first signal, or largest volume')
print('  Expected: 56 signals -> ~15-20 clusters -> ~15-20 signals')
print('  Pros: Captures key moments, reduces redundancy')
print('  Cons: More complex logic')

print('\n[Strategy 4: Progressive Filtering]')
print('  Apply multiple filters in sequence:')
print('  1. Time-based cooldown (reduce immediate duplicates)')
print('  2. Quality threshold (remove weak signals)')
print('  3. Cluster best-signal (within dense periods)')
print('  Expected: 56 signals -> ~3-5 best signals')
print('  Pros: Most robust, highest quality')
print('  Cons: Complex, may be too conservative')

print('\n[Strategy 5: Signal Aggregation]')
print('  Aggregate signals in a cluster into one composite signal')
print('  Aggregate logic: avg(strength), max(volume), weighted price')
print('  Expected: 56 signals -> ~15-20 aggregated signals')
print('  Pros: Preserves information from all signals')
print('  Cons: Loses precise timing information')

print('\n' + '='*80)
