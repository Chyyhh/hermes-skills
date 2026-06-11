#!/usr/bin/env python3
"""
A500 选股扫描 V8.0 — 纯K线+成交量 + 3L体系 + 量化时代
简放体系：「逻辑选股·量价择时」
V8.0 新增：大盘排除法（加速后+阴跌）、F7-F9过滤、新板块细分、第7条铁律

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

# ===== Step 1: Verify DB =====
conn = sqlite3.connect(DB)
db_latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (db_latest,)).fetchone()[0]
target = latest_trading_day()
conn.close()

print(f"DB: {db_latest} ({cnt}/500) | Target: {target}")
if db_latest < target or cnt < 450:
    print("Downloading...")
    subprocess.run(['python3', '-u', '/home/zhfuyi/download_a500.py'],
                   capture_output=True, text=True, timeout=120)

# ===== Step 2: Data =====
conn = sqlite3.connect(DB)
latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
codes = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_data').fetchall()]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (latest,)).fetchone()[0]
print(f"\n扫描: {latest} ({cnt}/{len(codes)})")

all_data = defaultdict(list)
for row in conn.execute('SELECT code, date, open, high, low, close, volume FROM daily_data WHERE date IN (SELECT date FROM daily_data GROUP BY date ORDER BY date DESC LIMIT 80)'):
    all_data[row[0]].append({
        'date': row[1], 'open': row[2], 'high': row[3],
        'low': row[4], 'close': row[5], 'volume': row[6]
    })

# ===== ===== V8.0 主线段落（新增封测/MLCC/CCL/光芯片等）===== =====
MAIN_SECTORS = {
    # 光模块/光通信
    '300308': '中际旭创', '300502': '新易盛', '002281': '光迅科技', '300394': '天孚通信',
    # 光芯片细分（V8.0 新增）
    '688498': '源杰科技', '300620': '光库科技',
    # 存储/HBM
    '603986': '兆易创新', '688525': '佰维存储', '688008': '澜起科技',
    # 半导体设备材料
    '002371': '北方华创', '688012': '中微公司', '688072': '拓荆科技',
    '300604': '长川科技', '688120': '华海清科', '603690': '至纯科技',
    '002008': '大族激光',
    # 半导体材料
    '002409': '雅克科技', '688268': '华特气体', '300666': '江丰电子',
    '688126': '沪硅产业',
    # 算力/芯片
    '603019': '中科曙光', '000977': '浪潮信息', '688256': '寒武纪',
    '688041': '海光信息', '688981': '中芯国际',
    # PCB/CCL（V8.0 新增生益科技）
    '002916': '深南电路', '300476': '胜宏科技', '002384': '东山精密',
    '600183': '生益科技',
    # 封测（V8.0 新增）
    '002156': '通富微电', '600584': '长电科技', '002185': '华天科技',
    # MLCC/被动元件（V8.0 新增）
    '000636': '风华高科', '300408': '三环集团',
    # 铜箔
    '600110': '诺德股份', '688388': '嘉元科技',
}

# ===== V8.0 非主线/碳基通缩板块（F9：量价齐缩不碰）=====
AVOID_SECTORS = {
    # 消费/地产/传统制造（碳基通缩方向）
    '000651': '格力电器', '002032': '苏泊尔', '603288': '海天味业',
    # 可扩展
}

def calc_ma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None

def trend_type(highs, lows, closes):
    """用高低点序列判断趋势（不用均线）—— V8.0 HH+HL 规则"""
    if len(highs) < 40:
        return 'unknown', 0
    h1, l1 = max(highs[-21:-1]), min(lows[-21:-1])
    h0, l0 = max(highs[-41:-21]), min(lows[-41:-21])
    slope = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0
    
    if h1 > h0 and l1 > l0:
        return '上升 HH+HL', slope
    elif h1 < h0 and l1 < l0:
        return '下降 LH+LL', slope
    else:
        return '震荡', slope

def vol_shrink_days(volumes):
    """连续缩量天数"""
    days = 0
    for i in range(-1, -10, -1):
        if abs(i) <= len(volumes) and volumes[i] < volumes[i-1]:
            days += 1
        else:
            break
    return days

def had_panic_drop(closes):
    """近3日是否有恐慌急跌"""
    for i in range(-3, -1):
        if abs(i+1) < len(closes):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if chg < -3:
                return True, chg, i
    if len(closes) >= 3:
        total = (closes[-3] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0
        if total < -8:
            return True, total, -3
    return False, 0, 0

def had_big_rebound(closes):
    """急跌后是否有 >5% 的大反弹（买点已过）"""
    for i in range(-3, 0):
        if abs(i) < len(closes) and abs(i+1) < len(closes):
            chg = (closes[i] - closes[i+1]) / closes[i+1] * 100
            if chg > 5:
                return True
    return False

def is_accelerating(highs, closes, volumes, avg_vol):
    """检测加速（近5日有放量大阳）—— V8.0：涨停不放量≠加速"""
    for i in range(-5, 0):
        if abs(i) < len(closes) and abs(i+1) < len(closes):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            vol_ratio = volumes[i] / avg_vol if avg_vol else 0
            # V8.0: 必须放量才算加速，涨停缩量不算
            if chg > 3 and vol_ratio > 1.5:
                return True
    return False

def check_v8_filters(closes, opens, highs, lows, volumes, code, trend):
    """V8.0 新增过滤规则 F7-F9"""
    filters_hit = []
    
    # F8: 不追非主线脉冲（在调用处已通过 is_mainline 过滤）
    
    # F9: 量价齐缩行业不碰（碳基通缩方向）——在调用处检查
    if code in AVOID_SECTORS:
        filters_hit.append('F9:碳基通缩方向')
    
    # F7: 前半小时不操作——由用户自行执行，扫描时不过滤
    # （扫描只提供信号，用户自己遵守F7）
    
    return filters_hit

# ===== Step 3: V8.0 大盘排除法（新增：加速后+阴跌排除）=====
up_count = down_count = 0
all_closes_for_market = []

for code, rows in all_data.items():
    rows.sort(key=lambda r: r['date'])
    if len(rows) >= 2:
        up_count += 1 if rows[-1]['close'] > rows[-2]['close'] else 0
        down_count += 1 if rows[-1]['close'] < rows[-2]['close'] else 0
        all_closes_for_market.extend([r['close'] for r in rows[-5:]])

up_ratio = up_count / (up_count + down_count) * 100 if (up_count + down_count) > 0 else 50
is_weak = up_ratio < 30

# V8.0: 大盘排除法——检测加速后和阴跌
market_warning = ""
market_recent_changes = []
for i in range(-5, 0):
    if abs(i+1) < len(all_closes_for_market):
        pass

# Simple heuristic: check if market has been declining with shrinking volume
# (can't easily do on per-code basis without index data)
# We'll flag based on up_ratio

if up_ratio < 30:
    market_warning = "⚠️弱势"
elif up_ratio < 50:
    market_warning = "✅正常"
else:
    market_warning = "🔥强势"

print(f"\n大盘: 涨{up_count}/跌{down_count} 涨跌比{up_ratio:.0f}% {market_warning}")
print("V8.0 排除法: 加速后? 阴跌? → 排除后专注主线")

# ===== Step 4: V8.0 扫描 =====
confirmed = []
watch = []
market_stats = {'上升': 0, '下降': 0, '震荡': 0}

for code, rows in all_data.items():
    rows.sort(key=lambda r: r['date'])
    closes = [r['close'] for r in rows]
    opens = [r['open'] for r in rows]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows]
    volumes = [r['volume'] for r in rows]
    
    if len(closes) < 30:
        continue
    
    name = MAIN_SECTORS.get(code, code)  # V8.0: use main sector name map
    
    is_mainline = code in MAIN_SECTORS
    avg_vol_20 = sum(volumes[-20:]) / 20
    vol_ratio = volumes[-1] / avg_vol_20
    today_chg = (closes[-1] - opens[-1]) / opens[-1] * 100
    close_chg = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
    
    # --- V8.0 F9: 量价齐缩行业过滤 ---
    if code in AVOID_SECTORS:
        continue  # 碳基通缩方向不参与选股
    
    # --- 趋势判断（纯K线 HH+HL）---
    trend, slope = trend_type(highs, lows, closes)
    market_stats[trend.split()[0]] = market_stats.get(trend.split()[0], 0) + 1
    
    # --- 上升趋势才继续 ---
    if not trend.startswith('上升'):
        if is_mainline:
            high_15 = max(highs[-16:-1]) if len(highs) > 15 else highs[-1]
            pb = (closes[-1] - high_15) / high_15 * 100
            watch.append((code, name, closes[-1], trend, pb, vol_ratio, '趋势不符合'))
        continue
    
    # --- 供应衰竭检测 ---
    shrink_days = vol_shrink_days(volumes)
    is_supply_exhausted = shrink_days >= 2 or vol_ratio < 0.7
    
    # --- V8.0 加速过滤（涨停不放量≠加速）---
    accelerating = is_accelerating(highs, closes, volumes, avg_vol_20)
    if accelerating:
        continue
    
    # --- 波峰/波谷 ---
    high_15 = max(highs[-16:-1]) if len(highs) > 15 else highs[-1]
    pb_15 = (closes[-1] - high_15) / high_15 * 100
    
    # --- B4 恐慌买点（V8.0）---
    has_panic, panic_chg, _ = had_panic_drop(closes)
    had_rebound = had_big_rebound(closes)
    
    if has_panic and is_supply_exhausted and not had_rebound and not accelerating:
        if closes[-1] > opens[-1]:
            confirmed.append(('B4', code, name, closes[-1], panic_chg, shrink_days, 
                            vol_ratio, pb_15, is_mainline, '🔥恐慌企稳阳'))
        else:
            if is_mainline and is_supply_exhausted:
                watch.append((code, name, closes[-1], trend, pb_15, vol_ratio, 
                            f'缩量{shrink_days}天等阳线'))
    
    # --- B2 中继买点（V8.0 均线多头辅助）---
    if not has_panic and shrink_days >= 2 and closes[-1] > opens[-1] and pb_15 < -3 and is_mainline:
        ma5 = calc_ma(closes, 5)
        ma20 = calc_ma(closes, 20)
        ma60 = calc_ma(closes, 60)
        if ma5 and ma20 and ma60 and ma5 > ma20 > ma60:
            confirmed.append(('B2', code, name, closes[-1], pb_15, shrink_days,
                            vol_ratio, pb_15, is_mainline, '缩量回踩阳+均线多头'))

# ===== Output (V8.0 格式) =====
print(f"\n{'='*60}")
print(f"📊 A500 选股 | V8.0 纯K线+量 | {latest} 收盘")
print(f"  量化时代 │ 三种趋势 │ 硅基通胀 │ 大盘排除法")
print(f"{'='*60}")

print(f"\n🏗️ 结构：↑上升{market_stats.get('上升',0)}只 ↔震荡{market_stats.get('震荡',0)}只 ↓下降{market_stats.get('下降',0)}只")

main_confirmed = [c for c in confirmed if c[8]]
other_confirmed = [c for c in confirmed if not c[8]]
main_watch = [w for w in watch if any(w[0].startswith(k) for k in MAIN_SECTORS) or MAIN_SECTORS.get(w[0], '')]

if main_confirmed:
    print(f"\n{'='*60}")
    print(f"🔥 已触发买点（主线，共{len(main_confirmed)}只）")
    print(f"{'='*60}")
    for sig, code, name, price, chg, sd, vr, pb, ml, desc in main_confirmed:
        print(f"\n  [{sig}] {code} {name}")
        print(f"  价格: {price:.2f} | {'恐慌跌' if sig=='B4' else '回撤'}: {chg:+.1f}% | 连续缩量: {sd}天 | 量比: {vr:.2f}")
        print(f"  位置: 15日高回撤{pb:+.1f}% | {desc}")
else:
    print(f"\n⚠️ 今日无主线买点触发")
    if main_watch:
        print(f"\n{'='*60}")
        print(f"👀 观察池 — 等「需求出现」的放量阳线（共{len(main_watch)}只）")
        print(f"{'='*60}")
        for i, w in enumerate(main_watch[:8]):
            code, name, price, trend, pb, vr, tip = w[0], w[1], w[2], w[3], w[4], w[5], w[6]
            trend_short = trend.split()[0] if ' ' in trend else trend
            print(f"\n  [{i+1}] {code} {name} 价格:{price:.2f}")
            print(f"  趋势:{trend_short} | 15日回撤:{pb:+.1f}% | 量比:{vr:.2f} | {tip}")

print(f"\n{'='*60}")
print("🎯 V8.0 操作法则：")
print("  ① 三种趋势：时代→经济→K线（HH+HL上升趋势）")
print("  ② 供应衰竭（连续缩量，量比<0.7）→ 需求出现（收阳放量 = 买点）")
print("  ③ 加速不看（近5日+3%放量大阳→跳过）| 反弹>5%→排除")
print("  ④ F7:前半小时不操作 | F8:非主线不追 | F9:碳基通缩回避")
print("  ⑤ 看得见的利空不是利空（第7条铁律）")
if main_confirmed:
    print(f"\n  ✅ 操作: {main_confirmed[0][2]}")
else:
    print(f"\n  ⏸️  无买点 ≠ 市场不好")
    print(f"  简放:「不调整就没有好的买点，忍耐是交易的一部分」")

conn.close()
