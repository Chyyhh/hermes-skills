"""A500 四阶段选股扫描 - 基于 trading-model V3
先自动校验数据库是否为最新，再扫描选股。
"""
import sqlite3, json, subprocess, sys
from datetime import datetime, date, timedelta
from collections import defaultdict

DB = '/home/zhfuyi/astock_a500.db'

def is_trading_day(d):
    """简单判断：周一到周五"""
    return d.weekday() < 5

def latest_trading_day():
    """返回最近一个交易日（跳过周末）"""
    d = date.today()
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d.strftime('%Y-%m-%d')

# ===== 第一步：校验数据库是否最新 =====
conn = sqlite3.connect(DB)
db_latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (db_latest,)).fetchone()[0]
target = latest_trading_day()
conn.close()

print(f"DB最新: {db_latest} ({cnt}/500) | 目标: {target}")

if db_latest < target or cnt < 450:
    print(f"⚠️ 数据不是最新，先自动下载...")
    result = subprocess.run(
        ['python3', '-u', '/home/zhfuyi/download_a500.py'],
        capture_output=True, text=True, timeout=120
    )
    print(result.stdout.strip()[-200:] if len(result.stdout) > 200 else result.stdout.strip())
    if result.returncode != 0:
        print(f"❌ 下载失败: {result.stderr[-300:]}")
        sys.exit(1)

# ===== 第二步：扫描选股 =====
conn = sqlite3.connect(DB)
latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
codes = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_data').fetchall()]
cnt = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (latest,)).fetchone()[0]
print(f"扫描日期: {latest}, 可用: {cnt}/{len(codes)}只")

# Fetch all data for analysis (last 60 trading days)
all_data = defaultdict(list)
for code, date, open_, high, low, close, volume in conn.execute(
    'SELECT code, date, open, high, low, close, volume FROM daily_data WHERE code IN (SELECT code FROM daily_data WHERE date=?) ORDER BY code, date',
    (latest,)):
    all_data[code].append({
        'date': date, 'open': open_, 'high': high, 'low': low,
        'close': close, 'volume': volume
    })

results = {'B1': [], 'B2': [], 'B3': [], 'B5': [], 'all': []}

for code in codes:
    if code not in all_data or len(all_data[code]) < 30:
        continue
    bars = all_data[code]
    closes = [b['close'] for b in bars]
    volumes = [b['volume'] for b in bars]
    latest_bar = bars[-1]
    latest_close = latest_bar['close']
    latest_vol = latest_bar['volume']

    # MA20
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20

    # === Phase filtering ===
    # F5: 第四阶段排除 - 收盘价 < MA20
    if latest_close < ma20:
        continue

    # 计算趋势强度 (近10日涨幅)
    if len(closes) >= 11:
        trend_10d = (closes[-1] / closes[-11] - 1) * 100
    else:
        trend_10d = 0

    # 近5日阳量 vs 阴量
    yang_vol = []
    yin_vol = []
    yang_days = 0
    for i in range(-10, 0):
        if i >= -len(bars):
            if bars[i]['close'] >= bars[i]['open']:
                yang_vol.append(bars[i]['volume'])
                yang_days += 1
            else:
                yin_vol.append(bars[i]['volume'])
    avg_yang_vol = sum(yang_vol)/len(yang_vol) if yang_vol else 0
    avg_yin_vol = sum(yin_vol)/len(yin_vol) if yin_vol else 0

    # 近5日/20日均量
    vol_5 = sum(volumes[-5:]) / 5
    vol_20 = sum(volumes[-20:]) / 20
    vol_ratio = latest_vol / vol_20 if vol_20 > 0 else 1

    # 第二阶段确认: 价格>MA20>MA50 + 阳量>阴量 + 红肥绿瘦
    is_phase2 = (latest_close > ma20 > ma50) and (avg_yang_vol > avg_yin_vol * 0.8) and (yang_days >= 5)

    if not is_phase2:
        continue

    # 20日波动率
    highs = [b['high'] for b in bars[-20:]]
    lows = [b['low'] for b in bars[-20:]]
    daily_range = [(h-l)/l*100 for h,l in zip(highs, lows)]
    avg_range = sum(daily_range)/20

    change_pct = (latest_close - bars[-2]['close']) / bars[-2]['close'] * 100 if len(bars) >= 2 else 0

    stock_info = {
        'code': code, 'close': latest_close, 'change': change_pct,
        'vol_ratio': vol_ratio, 'trend_10d': trend_10d,
        'yang_days': yang_days, 'avg_range': avg_range
    }

    # === Buy point detection ===
    
    # B2 中继买点: 缩量回踩 (量比<0.7) + 趋势向上
    if vol_ratio < 0.7 and trend_10d > 0 and latest_close > bars[-2]['close']:
        # 回踩MA10/MA20附近
        ma10 = sum(closes[-10:])/10
        dist_to_ma10 = (latest_close - ma10) / ma10 * 100
        if -1 < dist_to_ma10 < 5:
            stock_info['buy_type'] = 'B2'
            stock_info['note'] = f'回踩MA10({dist_to_ma10:.1f}%)'
            results['B2'].append(stock_info)
            continue

    # B1 突破买点: 放量(量比>1.5)突破20日高点
    if vol_ratio > 1.5:
        high_20 = max(bars[i]['high'] for i in range(-20, 0))
        if latest_close > high_20 * 0.98:  # 接近或突破
            stock_info['buy_type'] = 'B1'
            stock_info['note'] = f'突破20日高'
            results['B1'].append(stock_info)
            continue

    # B3 反转买点: 前日放量阴+今日放量阳
    if len(bars) >= 3 and vol_ratio > 1.2:
        prev = bars[-2]
        prev2 = bars[-3]
        if prev['close'] < prev['open'] and prev['volume'] > vol_20 * 1.3:  # 前日放量阴
            if latest_close > latest_bar['open'] and latest_close > prev['close']:  # 今日阳线反包
                stock_info['buy_type'] = 'B3'
                stock_info['note'] = '放量阳反包'
                results['B3'].append(stock_info)
                continue

    # B5 衰竭买点: 连续缩量3日+波动收窄
    if len(volumes) >= 4:
        v3 = [volumes[-4], volumes[-3], volumes[-2], volumes[-1]]
        if all(v3[i] < v3[i-1] for i in range(1, 4)) and vol_ratio < 0.5:
            stock_info['buy_type'] = 'B5'
            stock_info['note'] = '连续缩量衰竭'
            results['B5'].append(stock_info)
            continue

# Sort: B2 by trend desc, B1 by vol_ratio desc, B3 by change desc
results['B2'].sort(key=lambda x: x['trend_10d'], reverse=True)
results['B1'].sort(key=lambda x: x['vol_ratio'], reverse=True)
results['B3'].sort(key=lambda x: x['change'], reverse=True)

# Output
def fmt_pct(v):
    return f"{v:+.1f}%" if v else "0%"

print(f"\n{'='*60}")
print(f"📊 A500 盘后选股 | {latest} 收盘")
print(f"{'='*60}")

if results['B2']:
    print(f"\n🏆 B2 中继买点（缩量回踩，止损近，胜率最高）共{len(results['B2'])}只")
    print(f"{'代码':<10}{'收盘':>8}{'涨跌':>8}{'量比':>6}{'回踩':>12}{'趋势10d':>8}")
    print("-"*54)
    for s in results['B2'][:5]:
        print(f"{s['code']:<10}{s['close']:>8.2f}{s['change']:>+7.1f}%{s['vol_ratio']:>5.2f}{s['note']:>12}{s['trend_10d']:>+7.1f}%")
else:
    print("\n🏆 B2 中继买点：无")

if results['B1']:
    print(f"\n🔍 B1 突破买点（放量突破，止损远，风险较高）共{len(results['B1'])}只")
    print(f"{'代码':<10}{'收盘':>8}{'涨跌':>8}{'量比':>6}")
    for s in results['B1'][:5]:
        print(f"{s['code']:<10}{s['close']:>8.2f}{s['change']:>+7.1f}%{s['vol_ratio']:>5.2f}")
else:
    print("\n🔍 B1 突破买点：无")

if results['B3']:
    print(f"\n🔄 B3 反转买点（放量阳反包）共{len(results['B3'])}只")
    for s in results['B3'][:5]:
        print(f"  {s['code']} {s['close']:.2f} {fmt_pct(s['change'])} {s['note']}")
else:
    print("\n🔄 B3 反转买点：无")

if results['B5']:
    print(f"\n⏳ B5 衰竭买点（连续缩量，需等放量阳确认）共{len(results['B5'])}只")
    for s in results['B5'][:5]:
        print(f"  {s['code']} {s['close']:.2f} 量比{s['vol_ratio']:.2f} {s['note']}")

# 建议
print(f"\n{'='*60}")
print("🎯 操作建议：")
b2_codes = [s for s in results['B2'][:3]]
b1_codes = [s for s in results['B1'][:3]]

if b2_codes:
    print(f"🥇 优先(次日开盘观察)：{' / '.join(s['code'] for s in b2_codes)}")
    print(f"   理由：B2缩量回踩+收阳，供应衰竭明显，止损设在当日低点或MA20下方")
if b1_codes:
    print(f"🥉 可关注(等缩量回踩再进)：{' / '.join(s['code'] for s in b1_codes)}")
    print(f"   理由：B1突破买点止损远，不建议明日追，等缩量回踩5MA/10MA做B2")
if not b2_codes and not b1_codes:
    print("⚠️ 今日无高确定性买点，建议观望")

conn.close()
