#!/usr/bin/env python3
"""
3L体系 全信号回测引擎 (Backtest Engine)
回测一只股票在指定区间内的所有买卖信号

用法:
  python3 scripts/backtest_3l.py --code 600183 --start 2023-06-01
  python3 scripts/backtest_3l.py --scan          # 全市场扫描动量+买点
"""
import sqlite3, sys
import pandas as pd
import numpy as np

DB_PATH = "/home/zhfuyi/astock_a500.db"

def load_data(code, start="2023-01-01"):
    conn = sqlite3.connect(DB_PATH)
    raw = pd.read_sql_query("""
        SELECT date, open, high, low, close, volume
        FROM daily_data WHERE code=? AND date >= ? ORDER BY date
    """, conn, params=(code, start))
    conn.close()
    if raw.empty:
        print(f"Warning: no data for {code}")
        sys.exit(1)
    return raw

def calc_indicators(df):
    d = df.copy()
    for p in [5, 10, 20, 60, 120]:
        d[f'MA{p}'] = d['close'].rolling(p).mean()
    d['VOL_MA20'] = d['volume'].rolling(20).mean()
    d['VOL_RATIO'] = d['volume'] / d['VOL_MA20']
    return d

def detect_signals(d):
    """返回 [(date, type, detail, price), ...]"""
    sigs = []
    for i in range(120, len(d)):
        r = d.iloc[i]
        vr = r['VOL_RATIO']
        bull = bool(r['MA5'] > r['MA10'] > r['MA20'] > r['MA60'] > r['MA120'])
        
        # 买点1: 放量突破
        if bull and vr > 1.5 and r['close'] > r['MA20']:
            high_20d = d.iloc[i-20:i]['high'].max()
            if r['close'] > high_20d * 0.99:
                sigs.append(('BUY_突破', r['date'], f"量比{vr:.1f}", round(float(r['close']), 2)))
                continue
        
        # 买点2: 缩量回踩
        if bull and vr < 0.85 and r['MA20'] * 0.97 <= r['close'] <= r['MA20'] * 1.03:
            sigs.append(('BUY_回踩', r['date'], f"量比{vr:.1f}", round(float(r['close']), 2)))
            continue
        
        # 买点3: 多头启动
        if i >= 125:
            prev_bull = bool(d.iloc[i-5]['MA5'] > d.iloc[i-5]['MA10'] > d.iloc[i-5]['MA20'] > d.iloc[i-5]['MA60'] > d.iloc[i-5]['MA120'])
            if not prev_bull and bull and vr > 1.3:
                sigs.append(('BUY_多头启动', r['date'], f"量比{vr:.1f}", round(float(r['close']), 2)))
                continue
        
        # 卖点1: 跌破MA20
        prev = d.iloc[i-1]
        if prev['close'] > prev['MA20'] and r['close'] < r['MA20']:
            sigs.append(('SELL_跌破MA20', r['date'], f"{r['close']:.0f}<MA20{r['MA20']:.0f}", round(float(r['close']), 2)))
            continue
        
        # 卖点2: 放量滞涨
        if vr > 2.0 and r['close'] < r['MA5']:
            sigs.append(('SELL_放量滞涨', r['date'], f"量比{vr:.1f}", round(float(r['close']), 2)))
            continue
        
        # 卖点3: 死叉
        if prev['MA5'] > prev['MA10'] and r['MA5'] < r['MA10']:
            sigs.append(('SELL_死叉', r['date'], "", round(float(r['close']), 2)))
            continue
    return sigs

def scan_market(df, threshold=0.8):
    """全市场扫描：缩量回踩 + 放量突破"""
    results = []
    for code, grp in df.groupby('code'):
        grp = grp.sort_values('date').reset_index(drop=True)
        if len(grp) < 120:
            continue
        n = len(grp) - 1
        c, v = grp['close'].values, grp['volume'].values
        ma5 = np.mean(c[n-4:n+1])
        ma20 = np.mean(c[n-19:n+1])
        ma60 = np.mean(c[n-59:n+1])
        bull = ma5 > ma20 > ma60
        if not bull:
            continue
        
        vr = v[n] / max(np.mean(v[n-19:n+1]), 1)
        lb = min(15, n)
        hi = np.argmax(c[n-lb:n+1]) + (n - lb)
        pullback = (c[hi] - c[n]) / max(c[hi], 0.01) * 100 if c[hi] > 0 else 0
        dist_ma20 = (c[n] - ma20) / max(ma20, 0.01) * 100 if ma20 > 0 else 0
        
        if 2 <= pullback <= 15 and vr < threshold and c[n] >= ma60 and abs(dist_ma20) <= 15:
            score = 0
            if abs(dist_ma20) <= 3: score += 3
            if vr < 0.6: score += 2
            if pullback < 8: score += 1
            results.append((code, c[n], pullback, vr, ma20, dist_ma20, n-hi, score, 'B'))
        
        if vr > 1.5 and n >= 20:
            high_20d = max(c[n-19:n+1])
            if c[n] >= high_20d * 0.99 and c[n] > c[n-1]:
                results.append((code, c[n], 0, vr, ma20, dist_ma20, n-hi, 0, 'R'))
    
    results.sort(key=lambda r: (-r[7], r[2]))
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    
    if args.scan:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(
            "SELECT code, date, close, volume FROM daily_data WHERE date >= '2024-01-01' ORDER BY code, date",
            conn)
        name_df = pd.read_sql("SELECT DISTINCT code, name FROM a500_constituents", conn)
        name_map = dict(zip(name_df['code'], name_df['name']))
        conn.close()
        
        results = scan_market(df, args.threshold)
        pb = [r for r in results if r[8] == 'B']
        br = [r for r in results if r[8] == 'R']
        
        print(f"\nScan: {len(pb)} pullback + {len(br)} breakout")
        if pb:
            print(f"\n  Pullback (top by score):")
            for r in pb[:20]:
                print(f"  {r[0]} {name_map.get(r[0],''):10s} {r[1]:>8.2f} -{r[2]:.1f}% vr:{r[3]:.2f} ma20:{r[4]:.2f} dist:{r[5]:+.1f}% score:{r[7]}")
        if br:
            print(f"\n  Breakout (vr>1.5):")
            for r in br[:15]:
                print(f"  {r[0]} {name_map.get(r[0],''):10s} {r[1]:>8.2f} vr:{r[3]:.2f} dist:{r[5]:+.1f}%")
    
    elif args.code:
        d = calc_indicators(load_data(args.code, args.start))
        sigs = detect_signals(d)
        print(f"\n{args.code} — {len(sigs)} signals ({d['date'].iloc[0]}~{d['date'].iloc[-1]}, {len(d)} bars)")
        for s in sigs:
            print(f"  {s[1]} {s[0]:15s} {s[2]:20s} @{s[3]:.2f}")
    else:
        parser.print_help()
