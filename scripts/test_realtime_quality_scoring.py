"""
Real-Time Signal Quality Assessment System
Identify high-winrate signals EARLY without waiting for cluster completion
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

print('='*80)
print('Real-Time Signal Quality Assessment Test')
print('='*80)
print('Goal: Identify high-winrate signals EARLY (no waiting for clusters)')
print('')

# ============================================================================
# 1. Configuration - Optimized for Early High-Winrate Signals
# ============================================================================

print('[Configuration]')
MIN_CONFIRMATION_COUNT = 3  # Increased from 2 to 3 (user requirement)
MIN_BREAKOUT_STRENGTH = 2.5
WINDOW_SIZE = 200
CONFIRMATION_WINDOW_MS = 5000

# Quality scoring thresholds
QUALITY_THRESHOLD = 0.7  # Only execute signals with score >= 0.7
SIGNAL_COOLDOWN_SECONDS = 300  # 5 minutes cooldown after execution

print(f'  Minimum Confirmation Count: {MIN_CONFIRMATION_COUNT} (upgraded from 2)')
print(f'  Minimum Breakout Strength: {MIN_BREAKOUT_STRENGTH}')
print(f'  Quality Threshold: {QUALITY_THRESHOLD} (early filtering)')
print(f'  Signal Cooldown: {SIGNAL_COOLDOWN_SECONDS}s (prevent duplicate trades)')
print('')

# ============================================================================
# 2. Load Data
# ============================================================================

print('[Loading Data]')

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

# ============================================================================
# 3. Real-Time Quality Scoring System
# ============================================================================

class RealTimeQualityScorer:
    """
    Calculate signal quality score IMMEDIATELY when signal is generated
    Using forward-looking indicators to predict win-rate
    """

    def __init__(self):
        self.last_execution_time = None
        self.execution_count = 0

    def calculate_quality_score(self, detection_list, tick_data, current_time, symbol):
        """
        Calculate quality score based on forward-looking indicators

        Args:
            detection_list: list of (algo_name, strength) tuples
            tick_data: current tick information
            current_time: signal timestamp
            symbol: trading pair

        Returns:
            quality_score: 0.0 to 1.0
            score_breakdown: dict with individual component scores
        """

        scores = {}
        weights = {}

        # === Component 1: Algorithm Diversity Score ===
        # More algorithms = higher confidence
        unique_algos = len(set(d[0] for d in detection_list))
        algo_diversity_score = min(1.0, unique_algos / 5.0)  # 5 algos max
        scores['algo_diversity'] = algo_diversity_score
        weights['algo_diversity'] = 0.20

        # === Component 2: Strength Consistency Score ===
        # Check if all algorithms have similar strength (consensus)
        strengths = [d[1] for d in detection_list]
        strength_mean = np.mean(strengths)
        strength_std = np.std(strengths)
        strength_cv = strength_std / strength_mean if strength_mean > 0 else 1.0

        # Lower CV = more consistent = higher score
        consistency_score = max(0.0, 1.0 - strength_cv)
        scores['strength_consistency'] = consistency_score
        weights['strength_consistency'] = 0.15

        # === Component 3: Combined Strength Score ===
        # Overall strength of the signal
        combined_strength = np.mean(strengths)
        # Normalize: 2.5 is min, 8.0 is excellent
        strength_score = min(1.0, (combined_strength - 2.5) / (8.0 - 2.5))
        strength_score = max(0.0, strength_score)
        scores['combined_strength'] = strength_score
        weights['combined_strength'] = 0.25

        # === Component 4: Volume Surge Score ===
        # Volume surge magnitude (from detection_list)
        volume_detection = [d for d in detection_list if 'VOLUME' in d[0]]
        if volume_detection:
            volume_strength = volume_detection[0][1]
            # volume_strength is (volume_ratio + z_score) / 2
            # High volume_ratio gets high score
            volume_score = min(1.0, (volume_strength - 2.0) / 6.0)
            volume_score = max(0.0, volume_score)
        else:
            volume_score = 0.3  # Penalty for no volume confirmation
        scores['volume_surge'] = volume_score
        weights['volume_surge'] = 0.20

        # === Component 5: Price Momentum Score ===
        # Z-score magnitude (statistical strength)
        statistical_detection = [d for d in detection_list if 'STATISTICAL' in d[0]]
        if statistical_detection:
            stat_strength = statistical_detection[0][1]
            # Higher z-score = stronger breakout
            momentum_score = min(1.0, (stat_strength - 2.5) / 5.0)
            momentum_score = max(0.0, momentum_score)
        else:
            momentum_score = 0.3  # Penalty for no statistical confirmation
        scores['price_momentum'] = momentum_score
        weights['price_momentum'] = 0.20

        # Calculate weighted average
        total_score = 0.0
        total_weight = 0.0
        for component, score in scores.items():
            total_score += score * weights[component]
            total_weight += weights[component]

        quality_score = total_score / total_weight if total_weight > 0 else 0.0

        score_breakdown = {
            'quality_score': quality_score,
            'algo_diversity': algo_diversity_score,
            'strength_consistency': consistency_score,
            'combined_strength': strength_score,
            'volume_surge': volume_score,
            'price_momentum': momentum_score,
            'unique_algos': unique_algos,
            'avg_strength': combined_strength,
            'strength_cv': strength_cv
        }

        return quality_score, score_breakdown

    def should_execute_signal(self, quality_score, current_time):
        """
        Decide whether to execute signal based on quality and cooldown

        Returns:
            should_execute: bool
            reason: str
        """

        # Check cooldown
        if self.last_execution_time is not None:
            time_since_last = pd.Timedelta(current_time - self.last_execution_time).total_seconds()
            if time_since_last < SIGNAL_COOLDOWN_SECONDS:
                remaining = SIGNAL_COOLDOWN_SECONDS - time_since_last
                return False, f'cooldown ({remaining:.0f}s remaining)'

        # Check quality threshold
        if quality_score < QUALITY_THRESHOLD:
            return False, f'low quality (score={quality_score:.2f} < {QUALITY_THRESHOLD})'

        return True, f'high quality (score={quality_score:.2f})'

    def record_execution(self, current_time):
        """Record that a signal was executed"""
        self.last_execution_time = current_time
        self.execution_count += 1

# ============================================================================
# 4. Simulate Real-Time Signal Processing
# ============================================================================

def simulate_realtime_processing(df, symbol):
    """Simulate real-time signal processing with quality scoring"""

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    # Algorithm detectors (simplified)
    algorithms = ['STATISTICAL', 'MOMENTUM', 'CONSECUTIVE', 'VOLUME', 'PATH']

    quality_scorer = RealTimeQualityScorer()
    pending_signals = []

    generated_signals = []
    filtered_signals = []
    executed_signals = []

    for i in range(WINDOW_SIZE, len(prices)):
        current_time = times[i]

        # Simulate algorithm detections
        detections = []

        # Calculate metrics
        window_prices = prices[i-WINDOW_SIZE:i]
        window_volumes = volumes[i-WINDOW_SIZE:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)
        valid_volumes = window_volumes[window_volumes > 0]
        avg_volume = np.mean(valid_volumes) if len(valid_volumes) > 0 else 0

        if std_price > 0 and avg_volume > 0:
            z_score = (prices[i] - mean_price) / std_price
            volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

            # Check which algorithms trigger
            if abs(z_score) >= 2.5 and volume_ratio >= 2.0:
                # All algorithms trigger with same strength (simplified)
                strength = (abs(z_score) + volume_ratio) / 2
                for algo in algorithms:
                    detections.append((algo, strength))

        # Check minimum confirmation
        if len(detections) < MIN_CONFIRMATION_COUNT:
            continue

        # Add to pending
        for algo_name, strength in detections:
            pending_signals.append({
                'type': algo_name,
                'strength': strength,
                'timestamp': current_time
            })

        # Clean expired
        pending_signals = [
            s for s in pending_signals
            if pd.Timedelta(current_time - s['timestamp']).total_seconds() * 1000 < CONFIRMATION_WINDOW_MS
        ]

        # Check confirmation
        if len(pending_signals) >= MIN_CONFIRMATION_COUNT:
            unique_detections = list(set((s['type'], s['strength']) for s in pending_signals))

            total_strength = sum(s['strength'] for s in pending_signals)
            avg_strength = total_strength / len(pending_signals)

            if avg_strength >= MIN_BREAKOUT_STRENGTH:
                # Generate signal
                signal = {
                    'index': i,
                    'time': current_time,
                    'price': prices[i],
                    'avg_strength': avg_strength,
                    'detection_count': len(set(s['type'] for s in pending_signals)),
                    'detections': unique_detections
                }
                generated_signals.append(signal)

                # === KEY: Real-time quality assessment ===
                quality_score, score_breakdown = quality_scorer.calculate_quality_score(
                    unique_detections,
                    None,  # tick_data
                    current_time,
                    symbol
                )

                # Add quality score to signal
                signal['quality_score'] = quality_score
                signal['score_breakdown'] = score_breakdown

                # === KEY: Should execute? ===
                should_execute, reason = quality_scorer.should_execute_signal(
                    quality_score,
                    current_time
                )

                signal['should_execute'] = should_execute
                signal['execution_reason'] = reason

                if should_execute:
                    quality_scorer.record_execution(current_time)
                    executed_signals.append(signal)
                else:
                    filtered_signals.append(signal)

                # Clear pending
                pending_signals = []

    return generated_signals, filtered_signals, executed_signals

# ============================================================================
# 5. Run Simulation
# ============================================================================

print('='*80)
print('Real-Time Signal Processing Simulation')
print('='*80)

generated, filtered, executed = simulate_realtime_processing(gunusdt_df, 'GUNUSDT')

print(f'\n[Signal Statistics]')
print(f'  Total signals generated: {len(generated)}')
print(f'  Signals filtered (low quality/cooldown): {len(filtered)}')
print(f'  Signals executed (high quality): {len(executed)}')
print(f'  Filter rate: {len(filtered) / len(generated) * 100:.1f}%')

if executed:
    print(f'\n[Executed Signals (High-Winrate Early Signals)]')
    for i, sig in enumerate(executed, 1):
        time_str = pd.Timestamp(sig['time']).strftime('%H:%M:%S')
        quality = sig['quality_score']
        reason = sig['execution_reason']
        algos = sig['detection_count']
        strength = sig['avg_strength']

        print(f'\n  Signal {i}:')
        print(f'    Time: {time_str}')
        print(f'    Quality Score: {quality:.3f} ({reason})')
        print(f'    Algorithms: {algos}')
        print(f'    Avg Strength: {strength:.2f}')
        print(f'    Price: ${sig["price"]:.4f}')

        # Show score breakdown
        breakdown = sig['score_breakdown']
        print(f'    Score Breakdown:')
        print(f'      Diversity: {breakdown["algo_diversity"]:.2f}')
        print(f'      Consistency: {breakdown["strength_consistency"]:.2f}')
        print(f'      Strength: {breakdown["combined_strength"]:.2f}')
        print(f'      Volume: {breakdown["volume_surge"]:.2f}')
        print(f'      Momentum: {breakdown["price_momentum"]:.2f}')

# ============================================================================
# 6. Analysis: Quality Distribution
# ============================================================================

print('\n' + '='*80)
print('Quality Score Distribution Analysis')
print('='*80)

if generated:
    quality_scores = [s['quality_score'] for s in generated]

    print(f'\n[Quality Score Statistics]')
    print(f'  Mean: {np.mean(quality_scores):.3f}')
    print(f'  Median: {np.median(quality_scores):.3f}')
    print(f'  Std: {np.std(quality_scores):.3f}')
    print(f'  Min: {np.min(quality_scores):.3f}')
    print(f'  Max: {np.max(quality_scores):.3f}')

    # Quality distribution
    print(f'\n[Quality Distribution]')
    bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels = ['0-0.5', '0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9-1.0']

    hist, _ = np.histogram(quality_scores, bins=bins)
    for i, (label, count) in enumerate(zip(labels, hist)):
        percentage = count / len(generated) * 100
        marker = ' <-- EXECUTE' if 0.7 <= bins[i] else ''
        print(f'  {label}: {count:2d} signals ({percentage:5.1f}%){marker}')

    # Filter analysis
    print(f'\n[Filter Analysis]')
    filter_reasons = defaultdict(int)
    for sig in filtered:
        reason = sig['execution_reason'].split('(')[0].strip()
        filter_reasons[reason] += 1

    print(f'  Filter reasons:')
    for reason, count in sorted(filter_reasons.items(), key=lambda x: -x[1]):
        print(f'    {reason}: {count} signals')

# ============================================================================
# 7. Summary and Recommendations
# ============================================================================

print('\n' + '='*80)
print('Summary and Configuration Recommendations')
print('='*80)

print(f'\n[Current Configuration]')
print(f'  MIN_CONFIRMATION_COUNT: {MIN_CONFIRMATION_COUNT} (3+ algorithms)')
print(f'  MIN_BREAKOUT_STRENGTH: {MIN_BREAKOUT_STRENGTH}')
print(f'  QUALITY_THRESHOLD: {QUALITY_THRESHOLD}')
print(f'  SIGNAL_COOLDOWN_SECONDS: {SIGNAL_COOLDOWN_SECONDS}')

print(f'\n[Results]')
print(f'  Original signals: {len(generated)}')
print(f'  After quality filter: {len(executed)}')
print(f'  Reduction rate: {(1 - len(executed) / len(generated)) * 100:.1f}%')

if len(generated) > 0:
    print(f'\n[Effectiveness Analysis]')
    print(f'  Average time between executed signals: ', end='')
    if len(executed) > 1:
        time_diffs = [
            pd.Timedelta(executed[i+1]['time'] - executed[i]['time']).total_seconds()
            for i in range(len(executed) - 1)
        ]
        print(f'{np.mean(time_diffs) / 60:.1f} minutes')
    else:
        print('N/A (only 1 signal)')

    print(f'\n[Recommendation]')
    if len(executed) <= 3:
        print(f'  [GOOD] Only {len(executed)} high-quality signals selected')
        print(f'  Current quality threshold (0.7) is working well')
    elif len(executed) <= 5:
        print(f'  [OK] {len(executed)} signals is reasonable')
        print(f'  Could increase QUALITY_THRESHOLD to 0.75 for more filtering')
    else:
        print(f'  [WARN] {len(executed)} signals may still be too many')
        print(f'  Suggest increasing QUALITY_THRESHOLD to 0.75-0.80')

print('\n' + '='*80)
