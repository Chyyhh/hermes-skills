#!/usr/bin/env python3
"""
3L体系缩量回踩选股器
用法: python3 scripts/pullback_scanner.py [--db /home/zhfuyi/astock_a500.db]
"""
import sqlite3, sys, json
import pandas as pd
import numpy as np

DB_PATH = "/home/zhfuyi/astock_a500.db"
if len(sys.argv) > 2 and sys.argv[1] == '--db':
    DB_PATH = sys.argv[2]

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT code, date, close, volume FROM daily_data WHERE date >= '2025-01-01' ORDER BY code, date", conn)
name_df = pd.read_sql("SELECT DISTINCT code, name FROM a500_constituents WHERE name IS NOT NULL", conn)
name_map = dict(zip(name_df['code'], name_df['name']))
conn.close()

results = []
for code, grp in df.groupby('code'):
    grp = grp.sort_values('date').reset_index(drop=True)
    n = len(grp) - 1
    if n < 60: continue
    
    c, v = grp['close'].values, grp['volume'].values
    ma5, ma20, ma60 = np.mean(c[n-4:n+1]), np.mean(c[n-19:n+1]), np.mean(c[n-59:n+1])
    
    if not (ma5 > ma20 > ma60): continue  # 非多头
    
    lb = min(15, n)
    hi = np.argmax(c[n-lb:n+1]) + (n - lb)
    pullback = (c[hi] - c[n]) / c[hi] * 100
    v20 = np.mean(v[n-19:n+1])
    dist = (c[n] - ma20) / ma20 * 100
    
    if (2 <= pullback <= 15 and v[n] < v20 * 0.8 and n - hi >= 2 
        and n - hi <= 20 and c[n] >= ma60):
        results.append({
            'code': code, 'name': name_map.get(code, ''),
            'close': round(c[n], 2), 'pullback_pct': round(pullback, 1),
            'vol_ratio': round(v[n]/v20, 2), 'ma20': round(ma20, 2),
            'dist_ma20_pct': round(dist, 1), 'days_down': n - hi,
            'signal': '✅ BUY' if abs(dist) <= 3 else '→ WATCH'
        })

results.sort(key=lambda r: (r['signal'] != '✅ BUY', abs(r['dist_ma20_pct']), r['vol_ratio']))

print(f"\n{'='*55}")
print(f"  3L 缩量回踩选股 — {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"={'='*55}")
print(f"  条件: 均线多头 + 回撤2-15% + 量<20日均量×0.8")
print(f"={'='*55}")
print(f"\n  命中: {len(results)} 只\n")

if results:
    print(f"  {'代码':>8} {'名称':<10} {'价':>8} {'回撤':>6} {'量比':>6} {'MA20':>8} {'偏离':>6} {'信号':>10}")
    print(f"  {'─'*62}")
    for r in results:
        print(f"  {r['code']:>8} {r['name']:<10} {r['close']:>8.2f} {r['pullback_pct']:>5.1f}% {r['vol_ratio']:>5.2f} {r['ma20']:>8.2f} {r['dist_ma20_pct']:>+5.1f}% {r['signal']:>10}")
