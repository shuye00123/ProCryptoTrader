"""
GMTUSDT Breakout Analysis - Simplified
"""

import pandas as pd
import numpy as np

def calculate_volume_ratio(df, window_size=200):
    """Calculate volume ratio"""
    volumes = df['last_quantity'].values
    volume_ratios = []

    for i in range(window_size, len(volumes)):
        window_volumes = volumes[i-window_size:i]
        avg_volume = np.mean(window_volumes[window_volumes > 0]) if np.any(window_volumes > 0) else 1

        if avg_volume > 0 and volumes[i] > 0:
            ratio = volumes[i] / avg_volume
            volume_ratios.append(ratio)
        else:
            volume_ratios.append(0.0)

    return [0.0] * window_size + volume_ratios

def calculate_z_score(df, window_size=200):
    """Calculate Z-Score"""
    prices = df['price'].values
    z_scores = []

    for i in range(window_size, len(prices)):
        window_prices = prices[i-window_size:i]
        mean_price = np.mean(window_prices)
        std_price = np.std(window_prices)

        if std_price > 0:
            z_score = (prices[i] - mean_price) / std_price
            z_scores.append(z_score)
        else:
            z_scores.append(0.0)

    return [0.0] * window_size + z_scores

# Load data
print("=" * 80)
print("GMTUSDT Breakout Analysis")
print("=" * 80)

df1 = pd.read_parquet('data/tick/binance/GMTUSDT_2026010907.parquet')
df2 = pd.read_parquet('data/tick/binance/GMTUSDT_2026010908.parquet')
df3 = pd.read_parquet('data/tick/binance/GMTUSDT_2026010909.parquet')

df = pd.concat([df1, df2, df3], ignore_index=True)
df = df.sort_values('event_time').reset_index(drop=True)

print(f"\nData Overview:")
print(f"  Total ticks: {len(df):,}")
print(f"  Time range: {df['event_time'].min()} to {df['event_time'].max()}")

start_price = df['price'].iloc[0]
end_price = df['price'].iloc[-1]
max_price = df['price'].max()
min_price = df['price'].min()

total_return = ((end_price / start_price) - 1) * 100
volatility = ((max_price / min_price) - 1) * 100

print(f"  Price change: {start_price:.6f} -> {end_price:.6f}")
print(f"  Total return: {total_return:+.2f}%")
print(f"  Highest price: {max_price:.6f}")
print(f"  Lowest price: {min_price:.6f}")
print(f"  Volatility: {volatility:.2f}%")

# Calculate indicators
print(f"\nTechnical Indicators (window_size=200):")
df['z_score'] = calculate_z_score(df, 200)
df['volume_ratio'] = calculate_volume_ratio(df, 200)

valid_z = df['z_score'][df['z_score'] != 0]
valid_vol = df['volume_ratio'][df['volume_ratio'] != 0]

print(f"\nZ-Score Distribution:")
print(f"  Mean: {valid_z.mean():.2f}")
print(f"  Median: {valid_z.median():.2f}")
print(f"  Max: {valid_z.max():.2f}")
print(f"  Min: {valid_z.min():.2f}")
print(f"  Std: {valid_z.std():.2f}")

print(f"\nVolume Ratio Distribution:")
print(f"  Mean: {valid_vol.mean():.2f}x")
print(f"  Median: {valid_vol.median():.2f}x")
print(f"  Max: {valid_vol.max():.2f}x")
print(f"  Min: {valid_vol.min():.2f}x")

# Test different threshold combinations
print(f"\nBreakout Signals with Different Thresholds:")

thresholds = [
    (2.0, 2.0, "Loose Config (Z>=2.0, Vol>=2.0x)"),
    (2.5, 2.0, "Original Config (Z>=2.5, Vol>=2.0x)"),
    (2.5, 3.0, "Smart Original Config (Z>=2.5, Vol>=3.0x)"),
    (3.0, 5.0, "[CURRENT] Strict Config (Z>=3.0, Vol>=5.0x)"),
]

for z_thresh, vol_thresh, label in thresholds:
    breakouts = df[(df['z_score'].abs() >= z_thresh) & (df['volume_ratio'] >= vol_thresh)]
    count = len(breakouts)

    if count > 0:
        avg_z = breakouts['z_score'].abs().mean()
        avg_vol = breakouts['volume_ratio'].mean()
        max_vol = breakouts['volume_ratio'].max()
        print(f"\n{label}")
        print(f"  Signals: {count}")
        print(f"  Avg Z-Score: {avg_z:.2f}")
        print(f"  Avg Volume Ratio: {avg_vol:.2f}x")
        print(f"  Max Volume Ratio: {max_vol:.2f}x")
    else:
        print(f"\n{label}")
        print(f"  Signals: 0 [NO SIGNALS!]")

# Analyze why strict config produces no signals
print(f"\n" + "=" * 80)
print("Why Strict Config Produces No Signals - Deep Analysis")
print("=" * 80)

almost_z = df[df['z_score'].abs() >= 2.5]
almost_vol = df[df['volume_ratio'] >= 3.0]
almost_both = df[(df['z_score'].abs() >= 2.5) & (df['volume_ratio'] >= 3.0)]

print(f"\nSignals close to Z-Score threshold (Z>=2.5): {len(almost_z)}")
if len(almost_z) > 0:
    print(f"  Highest Z-Score: {almost_z['z_score'].abs().max():.2f}")
    print(f"  Average Volume Ratio: {almost_z['volume_ratio'].mean():.2f}x")

print(f"\nSignals close to Volume threshold (Vol>=3.0x): {len(almost_vol)}")
if len(almost_vol) > 0:
    print(f"  Highest Volume Ratio: {almost_vol['volume_ratio'].max():.2f}x")
    print(f"  Average Z-Score: {almost_vol['z_score'].abs().mean():.2f}")

print(f"\nSignals close to BOTH thresholds (Z>=2.5 AND Vol>=3.0x): {len(almost_both)}")

if len(almost_both) > 0:
    print(f"\n[!] These signals would trigger under loose config, but are filtered by strict config:")
    for idx, row in almost_both.head(15).iterrows():
        print(f"  {row['event_time']}: Z={row['z_score']:.2f}, Vol={row['volume_ratio']:.2f}x, Price={row['price']:.6f}")

# Comparison with BABYUSDT and GUNUSDT
print(f"\n" + "=" * 80)
print("Comparison with BABYUSDT/GUNUSDT")
print("=" * 80)

print(f"\nBABYUSDT (True Breakouts, future return >= 5%):")
print(f"  Z-Score: Mean 2.66, Median 2.69")
print(f"  Volume Ratio: Mean 59.74x, Median 8.11x")

print(f"\nBABYUSDT (False Breakouts, future return < 5%):")
print(f"  Z-Score: Mean 2.23, Median 2.75")
print(f"  Volume Ratio: Mean 11.86x, Median 3.97x")

print(f"\nGMTUSDT (This data):")
print(f"  Z-Score: Mean {valid_z.mean():.2f}, Median {valid_z.median():.2f}")
print(f"  Volume Ratio: Mean {valid_vol.mean():.2f}x, Median {valid_vol.median():.2f}x")

# Analysis and recommendations
print(f"\n" + "=" * 80)
print("CONCLUSION AND RECOMMENDATIONS")
print("=" * 80)

if len(almost_both) > 0:
    print(f"\n[!] GMTUSDT has {len(almost_both)} potential breakout signals")
    print(f"[X] But current strict config (Z>=3.0, Vol>=5.0x) is TOO STRICT")
    print(f"\n[KEY FINDINGS]:")
    print(f"  1. GMTUSDT Volume Ratio median ({valid_vol.median():.2f}x) is MUCH LOWER than BABYUSDT true breakouts (8.11x)")
    print(f"  2. GMTUSDT max Volume Ratio ({valid_vol.max():.2f}x) is also lower than BABYUSDT (59.74x)")
    print(f"  3. GMTUSDT has moderate price movement (+{total_return:.2f}%) but weaker volume confirmation")

    print(f"\n[RECOMMENDED CONFIG]:")
    print(f"  Option 1 - Balanced (RECOMMENDED):")
    print(f"    min_breakout_strength: 2.5 (from 3.0)")
    print(f"    volume_surge_threshold: 3.0 (from 5.0)")
    print(f"    quality_threshold: 0.75 (from 0.80)")
    print(f"    Expected: {len(almost_both)} signals")

    print(f"\n  Option 2 - Moderate:")
    print(f"    min_breakout_strength: 2.5")
    print(f"    volume_surge_threshold: 2.0")
    print(f"    quality_threshold: 0.70")
    print(f"    Expected: More signals, lower quality")

    print(f"\n  Option 3 - Adaptive Quality Scoring:")
    print(f"    Keep Z>=3.0, Vol>=5.0 for high threshold")
    print(f"    But lower quality_threshold to 0.70 to allow moderate signals")
else:
    print(f"\n[i] GMTUSDT indeed has no strong breakout signals in this period")

# Save detailed analysis
output_file = 'results/gmtusdt_breakout_analysis.csv'
if len(almost_both) > 0:
    almost_both[['event_time', 'price', 'z_score', 'volume_ratio']].to_csv(output_file, index=False)
    print(f"\n[*] Detailed analysis saved to: {output_file}")

print(f"\n" + "=" * 80)
