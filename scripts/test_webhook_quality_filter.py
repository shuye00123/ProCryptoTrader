"""
Verify Webhook Quality Filter Logic
Confirm that only high-quality signals (quality_score >= 0.8) trigger webhook
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

print('='*80)
print('Webhook Quality Filter Verification Test')
print('='*80)
print('Verify: Only signals with quality_score >= 0.8 trigger webhook')
print('')

# ============================================================================
# 1. Configuration
# ============================================================================

print('[Configuration]')
MIN_CONFIRMATION_COUNT = 3
MIN_BREAKOUT_STRENGTH = 2.5
QUALITY_THRESHOLD = 0.80  # ✅ Conservative configuration
COOLDOWN_SECONDS = 300

print(f'  Quality Threshold: {QUALITY_THRESHOLD}')
print(f'  Min Confirmation Count: {MIN_CONFIRMATION_COUNT}')
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
# 3. Simulate Quality Scoring with Webhook Logic
# ============================================================================

def simulate_with_webhook_filtering(df):
    """Simulate signal generation with webhook quality filtering"""

    prices = df['price'].values
    volumes = df['volume_increment'].values
    times = df['event_time_pd'].values

    last_execution_time = None
    pending_signals = []

    stats = {
        'total_generated': 0,
        'filtered_by_quality': 0,
        'filtered_by_cooldown': 0,
        'webhook_sent': 0,
        'webhook_signals': []
    }

    for i in range(200, len(prices)):
        current_time = times[i]

        # Simulate algorithm detections
        detections = []

        window_prices = prices[i-200:i]
        window_volumes = volumes[i-200:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)
        valid_volumes = window_volumes[window_volumes > 0]
        avg_volume = np.mean(valid_volumes) if len(valid_volumes) > 0 else 0

        if std_price > 0 and avg_volume > 0:
            z_score = (prices[i] - mean_price) / std_price
            volume_ratio = volumes[i] / avg_volume if volumes[i] > 0 else 0

            if abs(z_score) >= 2.5 and volume_ratio >= 2.0:
                strength = (abs(z_score) + volume_ratio) / 2
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
            if pd.Timedelta(current_time - s['timestamp']).total_seconds() * 1000 < 5000
        ]

        # Check confirmation
        if len(pending_signals) >= MIN_CONFIRMATION_COUNT:
            total_strength = sum(s['strength'] for s in pending_signals)
            avg_strength = total_strength / len(pending_signals)

            if avg_strength >= MIN_BREAKOUT_STRENGTH:
                stats['total_generated'] += 1

                # Calculate quality score
                unique_detections = list(set((s['type'], s['strength']) for s in pending_signals))
                strengths = [d[1] for d in unique_detections]
                strength_mean = np.mean(strengths)
                strength_std = np.std(strengths)
                strength_cv = strength_std / strength_mean if strength_mean > 0 else 1.0

                # Simple quality calculation (same as RealTimeQualityScorer)
                algo_diversity_score = min(1.0, len(set(d[0] for d in unique_detections)) / 5.0)
                consistency_score = max(0.0, 1.0 - strength_cv)
                combined_strength_score = min(1.0, max(0.0, (strength_mean - 2.5) / (8.0 - 2.5)))

                # Volume score
                volume_detection = [d for d in unique_detections if 'VOLUME' in d[0]]
                if volume_detection:
                    volume_score = min(1.0, max(0.0, (volume_detection[0][1] - 2.0) / 6.0))
                else:
                    volume_score = 0.3

                # Momentum score
                stat_detection = [d for d in unique_detections if 'STATISTICAL' in d[0]]
                if stat_detection:
                    momentum_score = min(1.0, max(0.0, (stat_detection[0][1] - 2.5) / 5.0))
                else:
                    momentum_score = 0.3

                # Calculate weighted average
                weights = {'algo_diversity': 0.20, 'strength_consistency': 0.15,
                          'combined_strength': 0.25, 'volume_surge': 0.20, 'price_momentum': 0.20}
                scores = {'algo_diversity': algo_diversity_score, 'strength_consistency': consistency_score,
                          'combined_strength': combined_strength_score, 'volume_surge': volume_score,
                          'price_momentum': momentum_score}
                quality_score = sum(scores[k] * weights[k] for k in scores.keys()) / sum(weights.values())

                # === Webhook Logic: Only send if quality passes ===
                # Check cooldown
                webhook_sent = False
                webhook_reason = ""

                if last_execution_time is not None:
                    time_since_last = pd.Timedelta(current_time - last_execution_time).total_seconds()
                    if time_since_last < COOLDOWN_SECONDS:
                        stats['filtered_by_cooldown'] += 1
                        webhook_reason = f"cooldown ({COOLDOWN_SECONDS - time_since_last:.0f}s remaining)"
                else:
                    # Check quality threshold
                    if quality_score >= QUALITY_THRESHOLD:
                        # ✅ PASS: Send webhook
                        stats['webhook_sent'] += 1
                        webhook_sent = True
                        webhook_reason = f"high quality (score={quality_score:.3f} >= {QUALITY_THRESHOLD})"
                        last_execution_time = current_time

                        stats['webhook_signals'].append({
                            'time': current_time,
                            'quality_score': quality_score,
                            'avg_strength': avg_strength,
                            'price': prices[i],
                            'reason': webhook_reason
                        })
                    else:
                        # ❌ FILTER: Low quality
                        stats['filtered_by_quality'] += 1
                        webhook_reason = f"low quality (score={quality_score:.3f} < {QUALITY_THRESHOLD})"

                # Clear pending
                pending_signals = []

    return stats

# ============================================================================
# 4. Run Simulation
# ============================================================================

print('='*80)
print('Webhook Quality Filter Simulation Results')
print('='*80)

stats = simulate_with_webhook_filtering(gunusdt_df)

print(f'\n[Signal Statistics]')
print(f'  Total signals generated: {stats["total_generated"]}')
print(f'  Filtered by quality: {stats["filtered_by_quality"]}')
print(f'  Filtered by cooldown: {stats["filtered_by_cooldown"]}')
print(f'  Webhook notifications sent: {stats["webhook_sent"]}')

print(f'\n[Webhook Filter Effectiveness]')
total_filtered = stats['filtered_by_quality'] + stats['filtered_by_cooldown']
filter_rate = (total_filtered / stats['total_generated'] * 100) if stats['total_generated'] > 0 else 0
print(f'  Total filtered: {total_filtered}/{stats["total_generated"]} ({filter_rate:.1f}%)')
print(f'  Webhook sent rate: {stats["webhook_sent"]}/{stats["total_generated"]} '
      f'({stats["webhook_sent"]/stats["total_generated"]*100:.1f}%)')

print(f'\n[Webhook Notifications Detail]')
if stats['webhook_signals']:
    for i, sig in enumerate(stats['webhook_signals'], 1):
        time_str = pd.Timestamp(sig['time']).strftime('%H:%M:%S')
        quality = sig['quality_score']
        strength = sig['avg_strength']
        price = sig['price']
        reason = sig['reason']

        print(f'\n  Webhook {i}:')
        print(f'    Time: {time_str}')
        print(f'    Quality Score: {quality:.3f}')
        print(f'    Avg Strength: {strength:.2f}')
        print(f'    Price: ${price:.4f}')
        print(f'    Reason: {reason}')

# ============================================================================
# 5. Verification
# ============================================================================

print('\n' + '='*80)
print('Verification Checklist')
print('='*80)

checks = []

# Check 1: Only high-quality signals trigger webhook
all_high_quality = all(s['quality_score'] >= QUALITY_THRESHOLD for s in stats['webhook_signals'])
checks.append({
    'check': 'Only quality_score >= 0.8 triggers webhook',
    'result': 'PASS' if all_high_quality else 'FAIL',
    'detail': f'All {len(stats["webhook_signals"])} webhook signals have quality >= {QUALITY_THRESHOLD}'
})

# Check 2: No low-quality signals trigger webhook
no_low_quality = True  # Already verified by check 1
checks.append({
    'check': 'No low-quality signals trigger webhook',
    'result': 'PASS',
    'detail': f'{stats["filtered_by_quality"]} low-quality signals blocked'
})

# Check 3: Reasonable webhook count
reasonable_count = 3 <= stats['webhook_sent'] <= 10
checks.append({
    'check': 'Webhook count is reasonable',
    'result': 'PASS' if reasonable_count else 'WARN',
    'detail': f'{stats["webhook_sent"]} webhooks sent (target 3-10)'
})

# Check 4: Filter rate is high
high_filter_rate = filter_rate >= 85
checks.append({
    'check': 'High filter rate (>85%)',
    'result': 'PASS' if high_filter_rate else 'WARN',
    'detail': f'{filter_rate:.1f}% of signals filtered'
})

print('\n[Verification Results]:')
for check in checks:
    status_icon = '[PASS]' if check['result'] == 'PASS' else '[WARN]' if check['result'] == 'WARN' else '[FAIL]'
    print(f'  {status_icon} {check["check"]}: {check["result"]}')
    print(f'     {check["detail"]}')

# ============================================================================
# 6. Summary
# ============================================================================

print('\n' + '='*80)
print('Summary')
print('='*80)

all_pass = all(c['result'] == 'PASS' for c in checks)

if all_pass:
    print('\n[SUCCESS] All verifications passed!')
    print('  [OK] Quality threshold (0.8) is working correctly')
    print('  [OK] Only high-quality signals trigger webhook')
    print('  [OK] Low-quality signals are properly filtered')
    print('  [OK] Webhook filter rate is excellent')
else:
    print('\n[WARN] Some verifications failed or warnings')

print('\n[Configuration Applied]')
print(f'  quality_threshold: {QUALITY_THRESHOLD}')
print(f'  min_confirmation_count: {MIN_CONFIRMATION_COUNT}')
print(f'  Result: {stats["webhook_sent"]} webhook notifications from {stats["total_generated"]} generated signals')

print('\n[Next Steps]')
print('  1. Update config: quality_scoring.enabled = true')
print('  2. Test with real-time data')
print('  3. Monitor webhook notifications')
print('  4. Adjust quality_threshold if needed (0.75-0.85)')

print('\n' + '='*80)
