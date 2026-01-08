"""
Quality Threshold Parameter Optimization Test
Find optimal quality_threshold by testing different values
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

print('='*80)
print('Quality Threshold Optimization Test')
print('='*80)
print('Test different quality_threshold values to find optimal configuration')
print('')

# ============================================================================
# 1. Configuration
# ============================================================================

print('[Configuration]')
MIN_CONFIRMATION_COUNT = 3  # 3+ algorithms
MIN_BREAKOUT_STRENGTH = 2.5
WINDOW_SIZE = 200
CONFIRMATION_WINDOW_MS = 5000

# Test different quality thresholds
QUALITY_THRESHOLDS_TO_TEST = [0.65, 0.70, 0.75, 0.80, 0.85]
COOLDOWN_SECONDS = 300

print(f'  Minimum Confirmation Count: {MIN_CONFIRMATION_COUNT}')
print(f'  Minimum Breakout Strength: {MIN_BREAKOUT_STRENGTH}')
print(f'  Quality Thresholds to Test: {QUALITY_THRESHOLDS_TO_TEST}')
print(f'  Cooldown: {COOLDOWN_SECONDS}s')
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
# 3. Quality Scoring System
# ============================================================================

class QualityScorer:
    """Quality scorer with configurable threshold"""

    def __init__(self, quality_threshold, cooldown_seconds):
        self.quality_threshold = quality_threshold
        self.cooldown_seconds = cooldown_seconds
        self.last_execution_time = None

    def calculate_quality_score(self, detection_list):
        """Calculate quality score"""
        scores = {}

        # Component 1: Algorithm Diversity
        unique_algos = len(set(d[0] for d in detection_list))
        algo_diversity_score = min(1.0, unique_algos / 5.0)
        scores['algo_diversity'] = algo_diversity_score

        # Component 2: Strength Consistency
        strengths = [d[1] for d in detection_list]
        strength_mean = np.mean(strengths)
        strength_std = np.std(strengths)
        strength_cv = strength_std / strength_mean if strength_mean > 0 else 1.0
        consistency_score = max(0.0, 1.0 - strength_cv)
        scores['strength_consistency'] = consistency_score

        # Component 3: Combined Strength
        combined_strength = strength_mean
        strength_score = min(1.0, max(0.0, (combined_strength - 2.5) / (8.0 - 2.5)))
        scores['combined_strength'] = strength_score

        # Component 4: Volume Surge
        volume_detection = [d for d in detection_list if 'VOLUME' in d[0]]
        if volume_detection:
            volume_strength = volume_detection[0][1]
            volume_score = min(1.0, max(0.0, (volume_strength - 2.0) / 6.0))
        else:
            volume_score = 0.3
        scores['volume_surge'] = volume_score

        # Component 5: Price Momentum
        statistical_detection = [d for d in detection_list if 'STATISTICAL' in d[0]]
        if statistical_detection:
            stat_strength = statistical_detection[0][1]
            momentum_score = min(1.0, max(0.0, (stat_strength - 2.5) / 5.0))
        else:
            momentum_score = 0.3
        scores['price_momentum'] = momentum_score

        # Calculate weighted average
        weights = {
            'algo_diversity': 0.20,
            'strength_consistency': 0.15,
            'combined_strength': 0.25,
            'volume_surge': 0.20,
            'price_momentum': 0.20
        }

        total_score = sum(scores[comp] * weights[comp] for comp in scores.keys())
        quality_score = total_score / sum(weights.values())

        return quality_score

    def should_execute(self, quality_score, current_time):
        """Check if signal should be executed"""
        # Check cooldown
        if self.last_execution_time is not None:
            time_since_last = pd.Timedelta(current_time - self.last_execution_time).total_seconds()
            if time_since_last < self.cooldown_seconds:
                return False

        # Check quality threshold
        if quality_score < self.quality_threshold:
            return False

        return True

    def record_execution(self, current_time):
        """Record execution time"""
        self.last_execution_time = current_time

# ============================================================================
# 4. Test Different Thresholds
# ============================================================================

def test_threshold(df, quality_threshold):
    """Test with specific quality threshold"""

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    scorer = QualityScorer(quality_threshold, COOLDOWN_SECONDS)
    pending_signals = []

    generated_signals = 0
    executed_signals = 0

    for i in range(WINDOW_SIZE, len(prices)):
        current_time = times[i]

        # Simulate algorithm detections
        detections = []

        window_prices = prices[i-WINDOW_SIZE:i]
        window_volumes = volumes[i-WINDOW_SIZE:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)
        valid_volumes = window_volumes[window_volumes > 0]
        avg_volume = np.mean(valid_volumes) if len(valid_volumes) > 0 else 0

        if std_price > 0 and avg_volume > 0:
            z_score = (prices[i] - mean_price) / std_price
            volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

            if abs(z_score) >= 2.5 and volume_ratio >= 2.0:
                strength = (abs(z_score) + volume_ratio) / 2
                # All 5 algorithms trigger
                for algo in ['STATISTICAL', 'MOMENTUM', 'CONSECUTIVE', 'VOLUME', 'PATH']:
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
            total_strength = sum(s['strength'] for s in pending_signals)
            avg_strength = total_strength / len(pending_signals)

            if avg_strength >= MIN_BREAKOUT_STRENGTH:
                generated_signals += 1

                # Calculate quality score
                unique_detections = list(set((s['type'], s['strength']) for s in pending_signals))
                quality_score = scorer.calculate_quality_score(unique_detections)

                # Check if should execute
                if scorer.should_execute(quality_score, current_time):
                    executed_signals += 1
                    scorer.record_execution(current_time)

                # Clear pending
                pending_signals = []

    return generated_signals, executed_signals

# ============================================================================
# 5. Run Tests
# ============================================================================

print('='*80)
print('Testing Different Quality Thresholds')
print('='*80)

results = []

for threshold in QUALITY_THRESHOLDS_TO_TEST:
    print(f'\n[Testing quality_threshold={threshold:.2f}]')
    generated, executed = test_threshold(gunusdt_df, threshold)

    filter_rate = (1 - executed / generated) * 100 if generated > 0 else 0
    reduction_rate = (1 - executed / 56) * 100 if 56 > 0 else 0  # Compared to original 56

    print(f'  Generated signals: {generated}')
    print(f'  Executed signals: {executed}')
    print(f'  Filter rate: {filter_rate:.1f}%')
    print(f'  Total reduction: {reduction_rate:.1f}% (from 56)')

    results.append({
        'threshold': threshold,
        'generated': generated,
        'executed': executed,
        'filter_rate': filter_rate,
        'reduction_rate': reduction_rate
    })

# ============================================================================
# 6. Analysis and Recommendation
# ============================================================================

print('\n' + '='*80)
print('Threshold Comparison and Recommendation')
print('='*80)

print(f'\n{"Threshold":<10} {"Generated":<12} {"Executed":<12} {"Filter Rate":<14} {"Reduction":<12}')
print('-' * 70)

for r in results:
    print(f'{r["threshold"]:<10.2f} {r["generated"]:<12} {r["executed"]:<12} '
          f'{r["filter_rate"]:<13.1f}% {r["reduction_rate"]:<11.1f}%')

print('\n[Recommendation]')

# Find optimal threshold
executed_counts = [r['executed'] for r in results]
ideal_count = 4  # Target around 4-6 signals

best_idx = min(range(len(results)), key=lambda i: abs(executed_counts[i] - ideal_count))
best_threshold = results[best_idx]['threshold']

print(f'\n  Recommended quality_threshold: {best_threshold:.2f}')
print(f'  Reason: Produces ~{results[best_idx]["executed"]} signals (target 4-6)')

# Additional analysis
print(f'\n[Quality vs Quantity Trade-off]')

for r in results:
    if r['executed'] <= 3:
        tradeoff = "Quality focus (few high-quality signals)"
    elif r['executed'] <= 6:
        tradeoff = "Balanced (optimal quality/quantity)"
    elif r['executed'] <= 10:
        tradeoff = "Moderate (more opportunities)"
    else:
        tradeoff = "Quantity focus (maximize opportunities)"

    print(f'  {r["threshold"]:.2f}: {tradeoff}')

print('\n[Configuration Examples]')
print(f'\nOption 1 - Conservative (highest quality):')
print(f'  quality_threshold: 0.85')
print(f'  Expected: ~{results[-1]["executed"]} signals')
print(f'  Use case: Only trade the best opportunities')

print(f'\nOption 2 - Balanced (recommended):')
print(f'  quality_threshold: {best_threshold:.2f}')
print(f'  Expected: ~{results[best_idx]["executed"]} signals')
print(f'  Use case: Balance quality and opportunity')

print(f'\nOption 3 - Aggressive (more opportunities):')
print(f'  quality_threshold: 0.65')
print(f'  Expected: ~{results[0]["executed"]} signals')
print(f'  Use case: Maximize trading opportunities')

# ============================================================================
# 7. BABYUSDT Validation
# ============================================================================

print('\n' + '='*80)
print('Validation with BABYUSDT')
print('='*80)

babyusdt_file = Path('data/tick/binance/BABYUSDT_2026010721.parquet')
if babyusdt_file.exists():
    babyusdt_df = pd.read_parquet(babyusdt_file)
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df['event_time_pd'] = pd.to_datetime(babyusdt_df['event_time'])
    babyusdt_df = babyusdt_df.sort_values('event_time_pd').reset_index(drop=True)
    babyusdt_df['volume_increment'] = babyusdt_df['volume'].diff().fillna(0)

    print(f'\n[BABYUSDT with recommended threshold={best_threshold:.2f}]')
    generated_baby, executed_baby = test_threshold(babyusdt_df, best_threshold)

    print(f'  Generated signals: {generated_baby}')
    print(f'  Executed signals: {executed_baby}')

    # Compare with GUNUSDT
    gunusdt_executed = results[best_idx]['executed']
    print(f'\n  Comparison:')
    print(f'    GUNUSDT: {gunusdt_executed} signals')
    print(f'    BABYUSDT: {executed_baby} signals')
    print(f'    Ratio: {executed_baby / gunusdt_executed if gunusdt_executed > 0 else 0:.2f}x')

    if 0.5 <= executed_baby / gunusdt_executed <= 2.0 if gunusdt_executed > 0 else True:
        print(f'    [PASS] Both symbols produce similar signal counts')
    else:
        print(f'    [WARN] Signal counts differ significantly')

print('\n' + '='*80)
print('Test Complete')
print('='*80)
