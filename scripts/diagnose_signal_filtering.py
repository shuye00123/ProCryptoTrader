"""
诊断信号过滤问题

检查为什么只推送了2个webhook信号
"""

import pandas as pd
import numpy as np
from pathlib import Path

print('='*80)
print('信号过滤问题诊断')
print('='*80)

# ============================================================================
# 配置分析
# ============================================================================

print('\n[1] 当前配置分析')
print('-'*80)

# 从配置文件读取的关键参数
config_params = {
    'direction_coordination.enabled': True,
    'direction_coordination.min_consensus_score': 0.65,
    'direction_coordination.min_confidence_threshold': 0.25,
    'direction_coordination.conflict_penalty': 0.2,
    'direction_coordination.max_conflicting_algos': 3,

    'require_multiple_confirmation': True,
    'min_confirmation_count': 3,
    'confirmation_window': 5000,  # 5秒

    'min_breakout_strength': 2.5,
    'volume_threshold': 2.0,
    'consecutive_moves_threshold': 5,

    'breakout_cooldown': 3000,  # 3秒
}

for key, value in config_params.items():
    print(f'  {key}: {value}')

# ============================================================================
# 方向协调机制过滤分析
# ============================================================================

print('\n[2] 方向协调机制过滤分析')
print('-'*80)

print('''
方向协调机制工作流程：

1️⃣ 收集5个算法的方向评分
   ├─ STATISTICAL: 买入/卖出强度
   ├─ MOMENTUM: 买入/卖出强度
   ├─ CONSECUTIVE: 买入/卖出强度
   ├─ VOLUME: 买入/卖出强度
   └─ PATH: 买入/卖出强度

2️⃣ 过滤低置信度信号
   ├─ 阈值: min_confidence_threshold = 0.25
   └─ ❌ 如果所有信号置信度 < 0.25 → 返回HOLD（不生成信号）

3️⃣ 加权计算共识分数
   ├─ 权重配置:
   │   ├─ STATISTICAL: 0.25
   │   ├─ MOMENTUM: 0.1
   │   ├─ CONSECUTIVE: 0.1
   │   ├─ VOLUME: 0.35
   │   └─ PATH: 0.2
   │
   ├─ 买入强度 = Σ(buy_strength × weight)
   ├─ 卖出强度 = Σ(sell_strength × weight)
   └─ 共识分数 = |买入强度 - 卖出强度| / 总权重

4️⃣ 冲突惩罚
   ├─ 如果同时有买入和卖出算法
   ├─ 冲突数 = min(买入算法数, 卖出算法数)
   ├─ 如果冲突数 > max_conflicting_algos (3):
   │   └─ 惩罚因子 = 1.0 - (0.2 × 冲突数 / 5)
   └─ 最终共识 = 共识分数 × 惩罚因子

5️⃣ ❌ 最终过滤（关键问题！）
   ├─ 阈值: min_consensus_score = 0.65
   ├─ 如果 final_consensus < 0.65 → 返回HOLD（不生成信号）
   └─ 只有 final_consensus >= 0.65 才生成BUY/SELL信号
''')

# ============================================================================
# 场景模拟
# ============================================================================

print('\n[3] 场景模拟：不同情况下的共识分数')
print('-'*80)

def simulate_consensus(buy_algos, sell_algos, algo_weights, conflict_penalty=0.2):
    """模拟共识计算"""

    # 计算权重
    buy_weight = sum(algo_weights.get(algo, 0.2) for algo in buy_algos)
    sell_weight = sum(algo_weights.get(algo, 0.2) for algo in sell_algos)
    total_weight = buy_weight + sell_weight

    # 共识分数
    if total_weight > 0:
        consensus_score = abs(buy_weight - sell_weight) / sum(algo_weights.values())
    else:
        consensus_score = 0.0

    # 冲突惩罚
    conflicting_count = min(len(buy_algos), len(sell_algos))
    penalty_factor = 1.0
    if conflicting_count > 3:
        penalty_factor = 1.0 - (conflict_penalty * conflicting_count / 5)

    final_consensus = consensus_score * penalty_factor

    return {
        'buy_weight': buy_weight,
        'sell_weight': sell_weight,
        'consensus_score': consensus_score,
        'conflicting_count': conflicting_count,
        'penalty_factor': penalty_factor,
        'final_consensus': final_consensus,
        'pass': final_consensus >= 0.65
    }

# 配置权重
algo_weights = {
    'STATISTICAL': 0.25,
    'MOMENTUM': 0.1,
    'CONSECUTIVE': 0.1,
    'VOLUME': 0.35,
    'PATH': 0.2
}

scenarios = [
    {
        'name': '场景1: 全部算法一致买入',
        'buy_algos': ['STATISTICAL', 'VOLUME', 'MOMENTUM', 'CONSECUTIVE', 'PATH'],
        'sell_algos': []
    },
    {
        'name': '场景2: 3个算法买入（VOLUME, STATISTICAL, PATH）',
        'buy_algos': ['VOLUME', 'STATISTICAL', 'PATH'],
        'sell_algos': []
    },
    {
        'name': '场景3: 2个算法买入（VOLUME, STATISTICAL）',
        'buy_algos': ['VOLUME', 'STATISTICAL'],
        'sell_algos': []
    },
    {
        'name': '场景4: 3买2卖（严重冲突）',
        'buy_algos': ['VOLUME', 'STATISTICAL', 'PATH'],
        'sell_algos': ['MOMENTUM', 'CONSECUTIVE']
    },
    {
        'name': '场景5: 1买4卖（严重冲突）',
        'buy_algos': ['VOLUME'],
        'sell_algos': ['STATISTICAL', 'MOMENTUM', 'CONSECUTIVE', 'PATH']
    },
]

for scenario in scenarios:
    result = simulate_consensus(
        scenario['buy_algos'],
        scenario['sell_algos'],
        algo_weights
    )

    status = '✅ PASS' if result['pass'] else '❌ FAIL'

    print(f"\n{scenario['name']}")
    print(f"  买入算法: {scenario['buy_algos']}")
    print(f"  卖出算法: {scenario['sell_algos']}")
    print(f"  买入权重: {result['buy_weight']:.3f}")
    print(f"  卖出权重: {result['sell_weight']:.3f}")
    print(f"  原始共识: {result['consensus_score']:.3f}")
    print(f"  冲突数: {result['conflicting_count']}")
    print(f"  惩罚因子: {result['penalty_factor']:.3f}")
    print(f"  最终共识: {result['final_consensus']:.3f}")
    print(f"  阈值: 0.65")
    print(f"  结果: {status}")

# ============================================================================
# 第二层过滤：确认窗口
# ============================================================================

print('\n\n[4] 第二层过滤：确认窗口机制')
print('-'*80)

print('''
即使通过方向协调，还需要通过确认窗口：

1️⃣ 积累信号
   ├─ 在确认窗口内（5秒）积累至少3个信号
   └─ min_confirmation_count: 3

2️⃣ 方向一致性检查
   ├─ 计算窗口内买入/卖出信号比例
   ├─ 需要至少70%的方向一致性
   └─ 如果买入3个、卖出0个 → 一致性100% ✅
   └─ 如果买入2个、卖出1个 → 一致性66% ❌

3️⃣ 第三层：算法强度阈值
   ├─ min_breakout_strength: 2.5
   ├─ volume_threshold: 2.0
   └─ consecutive_moves_threshold: 5
''')

# ============================================================================
# 总结：问题根源
# ============================================================================

print('\n[5] 问题根源总结')
print('='*80)

print('''
🚨 核心问题：方向协调机制的 min_consensus_score = 0.65 太严格！

分析：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 场景2（3个算法买入）：
   买入权重 = 0.35 (VOLUME) + 0.25 (STATISTICAL) + 0.2 (PATH) = 0.80
   最终共识 = 0.80 / 1.0 = 0.80
   结果: ✅ PASS（勉强通过）

❌ 场景3（2个算法买入）：
   买入权重 = 0.35 (VOLUME) + 0.25 (STATISTICAL) = 0.60
   最终共识 = 0.60 / 1.0 = 0.60
   结果: ❌ FAIL（低于0.65阈值）

❌ 场景4（3买2卖，有冲突）：
   买入权重 = 0.35 + 0.25 + 0.2 = 0.80
   卖出权重 = 0.1 + 0.1 = 0.20
   原始共识 = (0.80 - 0.20) / 1.0 = 0.60
   冲突数 = min(3, 2) = 2（未超过3，无惩罚）
   最终共识 = 0.60
   结果: ❌ FAIL（低于0.65阈值）

✅ 场景5（1买4卖，严重冲突）：
   买入权重 = 0.35
   卖出权重 = 0.25 + 0.1 + 0.1 + 0.2 = 0.65
   原始共识 = (0.65 - 0.35) / 1.0 = 0.30
   结果: ❌ FAIL（远低于0.65）

结论：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 只有满足以下条件才能生成信号：
   1. 至少3个高权重算法一致（如 VOLUME+STATISTICAL+PATH）
   2. 不能有超过3个的冲突算法
   3. 买卖强度差值必须达到总权重的65%
   4. 还要通过确认窗口的3个信号积累
   5. 还要满足70%的方向一致性

🔴 这就是为什么只推送了2个webhook信号！
   大部分时间市场无法满足如此严格的条件。
''')

# ============================================================================
# 建议修复方案
# ============================================================================

print('\n[6] 建议修复方案')
print('='*80)

print('''
方案1：降低方向协调阈值（推荐）━━━━━━━━━━━━━━━━━━━━━━
修改 configs/hf_breakout_live_config.yaml:

  direction_coordination:
    enabled: true
    min_consensus_score: 0.45  # ✅ 从0.65降低到0.45（允许2个强算法）
    conflict_penalty: 0.15      # ✅ 从0.2降低到0.15（减少惩罚）
    max_conflicting_algos: 4    # ✅ 从3增加到4（更宽松）

效果预估：
  - 场景2（3算法）: 0.80 → ✅ PASS
  - 场景3（2算法）: 0.60 → ✅ PASS（从FAIL变成PASS）
  - 信号数量预计增加3-5倍


方案2：关闭方向协调机制（激进）━━━━━━━━━━━━━━━━━━━━━
修改 configs/hf_breakout_live_config.yaml:

  direction_coordination:
    enabled: false  # ✅ 完全关闭方向协调

效果：
  - 恢复到标准多因子确认模式
  - 信号数量预计增加5-10倍
  - 但可能增加信号噪音


方案3：调整确认窗口要求（平衡）━━━━━━━━━━━━━━━━━━━━━
修改 configs/hf_breakout_live_config.yaml:

  require_multiple_confirmation: true
  min_confirmation_count: 2  # ✅ 从3降低到2
  confirmation_window: 3000  # ✅ 从5000降低到3000（3秒）

效果：
  - 更快积累足够的确认信号
  - 信号数量预计增加2-3倍


方案4：降低算法强度阈值（保守）━━━━━━━━━━━━━━━━━━━━━
修改 configs/hf_breakout_live_config.yaml:

  tick_breakout:
    min_breakout_strength: 2.0    # ✅ 从2.5降低到2.0
    volume_threshold: 1.5          # ✅ 从2.0降低到1.5

效果：
  - 更多算法能够触发
  - 信号数量预计增加2-4倍


推荐组合：方案1 + 方案3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

direction_coordination:
  enabled: true
  min_consensus_score: 0.45  # 降低到0.45
  max_conflicting_algos: 4    # 增加到4

require_multiple_confirmation: true
  min_confirmation_count: 2  # 降低到2

预期效果：
  - 信号数量从 2个/天 → 20-50个/天
  - 保持合理的信号质量
  - 平衡敏感度和准确性
''')

print('\n' + '='*80)
print('诊断完成')
print('='*80)
