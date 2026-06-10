"""
A500 四阶段选股扫描 - 基于 trading-model V3
先自动校验数据库是否为最新（不足则调用 download_a500.py），再扫描选股。

用法: python3 scan_a500_buy.py
"""
import sqlite3, json, subprocess, sys
from datetime import datetime, date, timedelta
from collections import defaultdict

DB = '/home/zhfuyi/astock_a500.db'

def is_trading_day(d):
    return d.weekday() < 5

def latest_trading_day():
    d = date.today()
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d.strftime('%Y-%m-%d')

# ===== Step 1: Verify DB is current =====
conn = sqlite3.connect(DB)
db_latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (db_latest,)).fetchone()[0]
target = latest_trading_day()
conn.close()

print(f"DB: {db_latest} ({cnt}/500) | Target: {target}")

if db_latest < target or cnt < 450:
    print(f"Downloading...")
    result = subprocess.run(
        ['python3', '-u', '/home/zhfuyi/download_a500.py'],
        capture_output=True, text=True, timeout=120
    )
    print(result.stdout.strip()[-300:])

# ===== Step 2: Scan =====
conn = sqlite3.connect(DB)
latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
codes = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_data').fetchall()]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (latest,)).fetchone()[0]
print(f"\nScanning: {latest} ({cnt}/{len(codes)})")

# Load last 60 trading days
all_data = defaultdict(list)
dates_query = conn.execute(
    'SELECT DISTINCT date FROM daily_data ORDER BY date DESC LIMIT 60').fetchall()
dates_sorted = sorted([d[0] for d in dates_query])

for row in conn.execute(
    'SELECT code, date, open, high, low, close, volume FROM daily_data WHERE date IN (SELECT date FROM daily_data GROUP BY date ORDER BY date DESC LIMIT 60)'):
    all_data[row[0]].append({
        'date': row[1], 'open': row[2], 'high': row[3],
        'low': row[4], 'close': row[5], 'volume': row[6]
    })

def calc_ma(closes, n):
    if len(closes) < n: return None
    return sum(closes[-n:]) / n

def simple_ma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None

def is_limit_up(code, open_p, close_p, high_p, low_p, prev_close):
    """检测涨停板（含一字板）。
    
    涨停板（含一字板）的缩量是人为的——不是供应衰竭，而是极端需求导致无人卖出。
    必须排除，否则会被误判为 B5「连续缩量衰竭」。
    
    涨停幅度：主板 ±10%，科创/创业板 ±20%，北交所 ±30%
    """
    change_pct = (close_p - prev_close) / prev_close * 100 if prev_close else 0
    
    # 判断板块
    if code.startswith('688') or code.startswith('300') or code.startswith('301'):
        limit = 19.8  # 科创板/创业板 ±20%，容差0.2%
    elif code.startswith('8') or code.startswith('4'):
        limit = 29.5  # 北交所 ±30%
    else:
        limit = 9.8   # 主板 ±10%
    
    # 涨停判定：涨幅接近涨停板 且 收盘=最高（封板）
    if change_pct >= limit and close_p == high_p:
        return True
    
    # 一字板：开盘=最高=最低=收盘，涨幅接近涨停板
    if open_p == high_p == low_p == close_p and change_pct >= limit * 0.8:
        return True
    
    return False

# Buy point detection
b1, b2, b3, b5 = [], [], [], []

for code, rows in all_data.items():
    rows.sort(key=lambda r: r['date'])
    closes = [r['close'] for r in rows]
    volumes = [r['volume'] for r in rows]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows]
    
    if len(closes) < 30:
        continue
    
    ma20 = calc_ma(closes, 20)
    ma50 = calc_ma(closes, 50)
    latest_close = closes[-1]
    latest_vol = volumes[-1]
    
    # Phase 4 filter
    if latest_close < (ma20 or 0):
        continue
    
    # Phase 1 filter
    avg_vol_20 = sum(volumes[-20:]) / 20
    avg_vol_5 = sum(volumes[-5:]) / 5
    if avg_vol_5 < avg_vol_20 * 0.5:
        continue
    
    # Phase 2 check: price > MA20 > MA50 and bullish volume pattern
    if not (ma50 and ma20 and latest_close > ma20 and ma20 > ma50):
        continue
    
    # Volume pattern: yang avg > yin avg in last 10 days
    yang_vols, yin_vols = [], []
    for i in range(-10, 0):
        if closes[i] > closes[i-1]:
            yang_vols.append(volumes[i])
        else:
            yin_vols.append(volumes[i])
    avg_yang = sum(yang_vols) / len(yang_vols) if yang_vols else 0
    avg_yin = sum(yin_vols) / len(yin_vols) if yin_vols else float('inf')
    
    if avg_yang < avg_yin:
        continue
    
    # Vol ratio
    vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 else 0
    change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    
    name = conn.execute('SELECT name FROM (SELECT code, name FROM a500_constituents) WHERE code=?', (code,)).fetchone()
    name = name[0] if name else code
    
    # 涨停板判定：一字板/涨停板的缩量是人为的，必须排除
    limit_up = is_limit_up(code, rows[-1]['open'], closes[-1], highs[-1], lows[-1], prev_close)
    
    # B2: pullback on low volume (best)
    # 排除涨停板 —— 一字板/封板涨停的缩量不是正常的「缩量回踩」
    if not limit_up and vol_ratio < 0.7 and closes[-1] > closes[-2]:
        trend = (closes[-1] - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else 0
        b2.append((code, name, latest_close, change_pct, vol_ratio, trend, ma20))
    
    # B1: breakout (risky)
    high_20 = max(highs[-21:-1]) if len(highs) > 20 else max(highs[:-1])
    if latest_close > high_20 and vol_ratio > 1.5:
        b1.append((code, name, latest_close, change_pct, vol_ratio))
    
    # B3: bullish engulfing reversal
    if change_pct > 0 and closes[-2] < closes[-3] and vol_ratio > 1.2:
        b3.append((code, name, latest_close, change_pct))
    
    # B5: exhaustion (volume drying up) — 连续缩量+地量
    # ⚠️ 关键过滤：
    #   1. 排除涨停板 —— 一字板/封板缩量是人为的，不是供应衰竭
    #   2. 必须在回调/整理状态 —— 缩量发生在股价回调或横盘时，而非创新高
    #   3. 连续缩量至少3日 + 量比 < 0.3（极度缩量）
    if len(volumes) >= 3 and not limit_up:
        vol_decline = all(volumes[i] < volumes[i-1] for i in range(-1, -4, -1))
        # 确认处于回调状态：近5日高点 < 前5日高点（非创新高）
        recent_high = max(highs[-5:]) if len(highs) >= 5 else highs[-1]
        prior_high = max(highs[-10:-5]) if len(highs) >= 10 else recent_high
        in_pullback = recent_high <= prior_high * 1.02  # 不是创新高（容差2%）
        
        if vol_decline and vol_ratio < 0.3 and in_pullback:
            b5.append((code, name, latest_close, vol_ratio))

conn.close()

# === Output ===
print("\n" + "="*60)
print(f"📊 A500 盘后选股 | {latest} 收盘")
print("="*60)

if not b2:
    print("\n🏆 B2 中继买点：无")
else:
    print(f"\n🏆 B2 中继买点（缩量回踩，胜率最高）共{len(b2)}只")
    b2.sort(key=lambda x: x[5], reverse=True)
    for c, n, p, chg, vr, trend, ma in b2[:5]:
        print(f"  {c} {n:6s} {p:>8.2f} {chg:>+5.1f}% 量比{vr:.2f} 趋势{trend:+.1f}% MA20={ma:.1f}")

if not b1:
    print("\n🔍 B1 突破买点：无")
else:
    print(f"\n🔍 B1 突破买点（放量突破，止损远⚠️）共{len(b1)}只")
    b1.sort(key=lambda x: x[3], reverse=True)
    for c, n, p, chg, vr in b1[:5]:
        print(f"  {c} {n:6s} {p:>8.2f} {chg:>+5.1f}% 量比{vr:.2f}")

if not b3:
    print("\n🔄 B3 反转买点：无")
else:
    print(f"\n🔄 B3 反转买点（放量阳反包）共{len(b3)}只")
    for c, n, p, chg in b3[:5]:
        print(f"  {c} {n:6s} {p:>8.2f} {chg:>+5.1f}% 放量阳反包")

if not b5:
    print("\n⏳ B5 衰竭买点：无")
else:
    print(f"\n⏳ B5 衰竭买点（连续缩量，需等放量阳确认）共{len(b5)}只")
    for c, n, p, vr in b5[:3]:
        print(f"  {c} {n:6s} {p:>8.2f} 量比{vr:.2f} 连续缩量衰竭")

print("\n" + "="*60)
print("🎯 操作建议：")
if b2:
    print(f"🥇 优先操作 B2 中继买点，止损近胜率高")
if b3:
    print(f"🥈 B3 反转买点可轻仓试探")
if b1:
    top_b1 = [x[0] for x in b1[:3]]
    print(f"🥉 B1 突破({', '.join(top_b1)})止损远，等缩量回踩做B2")
if not (b1 or b2 or b3):
    print("今日无符合条件的买点信号")
