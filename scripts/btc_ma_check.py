"""BTC USDT 永续合约均线监控 — Gate.io REST API"""
import requests, numpy as np, json
from datetime import datetime

BASE = 'https://api.gateio.ws/api/v4/futures/usdt'
TIMEFRAMES = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h'}

def fetch_klines(interval, limit=200):
    url = f'{BASE}/candlesticks?contract=BTC_USDT&interval={interval}&limit={limit}'
    r = requests.get(url, timeout=10)
    return r.json()

def analyze(tf, klines):
    closes = np.array([float(k['c']) for k in klines])
    n = len(closes)
    
    ma7 = np.mean(closes[-7:])
    ma28 = np.mean(closes[-28:])
    ma84 = np.mean(closes[-84:]) if n >= 84 else None
    
    prev_ma7 = np.mean(closes[-8:-1])
    prev_ma28 = np.mean(closes[-29:-1])
    prev_ma84 = np.mean(closes[-85:-1]) if n >= 85 else None
    
    price = closes[-1]
    prev_price = closes[-2]
    
    # 三线方向
    m7_dir = '↑' if ma7 > prev_ma7 else '↓'
    m28_dir = '↑' if ma28 > prev_ma28 else '↓'
    m84_dir = '↑' if (ma84 and ma84 > prev_ma84) else '↓'
    
    # 排列
    if ma7 > ma28 and (ma84 is None or ma28 > ma84):
        arrange = '🟢 多头'
    elif ma7 < ma28 and (ma84 is None or ma28 < ma84):
        arrange = '🔴 空头'
    else:
        arrange = '⚪ 交叉'
    
    # 三线同步
    if m7_dir == m28_dir == m84_dir == '↑':
        sync = '🔥 三线↑↑↑'
    elif m7_dir == m28_dir == m84_dir == '↓':
        sync = '💧 三线↓↓↓'
    else:
        sync = f'7{m7_dir}28{m28_dir}84{m84_dir}'
    
    return {
        'price': price, 'ma7': ma7, 'ma28': ma28, 'ma84': ma84,
        'arrange': arrange, 'sync': sync, 'change': price - prev_price
    }

# Main
now = datetime.now()
print(f"⏰ {now.strftime('%Y-%m-%d %H:%M')} | BTC USDT 永续")

results = {}
for tf, interval in TIMEFRAMES.items():
    try:
        klines = fetch_klines(interval)
        results[tf] = analyze(tf, klines)
    except Exception as e:
        results[tf] = {'error': str(e)[:60]}

# Print table
print(f"{'周期':<6} {'现价':>10} {'7MA':>10} {'28MA':>12} {'84MA':>12} {'排列':<12} {'同步'}")
print("-" * 80)
for tf in ['1m','5m','15m','1h']:
    r = results[tf]
    if 'error' in r:
        print(f"{tf:<6} {'ERR':>10} {r['error']}")
    else:
        chg = f"{r['change']:+.1f}"
        print(f"{tf:<6} {r['price']:>10.1f} {r['ma7']:>10.1f} {r['ma28']:>12.1f} {r['ma84']:>12.1f} {r['arrange']:<12} {r['sync']}")

# 共振判断
arrs = [results[tf].get('arrange','') for tf in ['1m','5m','15m','1h']]
syncs = [results[tf].get('sync','') for tf in ['1m','5m','15m','1h']]

all_bull = all('多头' in a for a in arrs) and not any('error' in str(r) for r in results.values())
all_bear = all('空头' in a for a in arrs)
all_3up = all('三线↑' in s for s in syncs)
all_3dn = all('三线↓' in s for s in syncs)

print("\n" + "="*50)
if all_bull and all_3up:
    print("🚀 共振极致多头！全部多头排列+三线同步上升 → 做多")
elif all_bear and all_3dn:
    print("💥 共振极致空头！全部空头排列+三线同步下降 → 做空")
elif all_bull:
    print("🟢 四周期多头，但三线未完全同步 → 偏多观望等回调")
elif all_bear:
    print("🔴 四周期空头，但三线未完全同步 → 偏空观望")
else:
    print("⚪ 无共振信号，观望")
    status = []
    for tf in ['1m','5m','15m','1h']:
        a = results[tf].get('arrange','')
        status.append(f"{tf}:{'多' if '多头' in a else '空' if '空头' in a else '震'}")
    print(f"   {' | '.join(status)}")
