"""Download A500 daily data via Sina Finance API"""
import sqlite3, requests, time, json

DB = '/home/zhfuyi/astock_a500.db'
TARGET = '2026-06-09'

conn = sqlite3.connect(DB)
codes = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_data ORDER BY code').fetchall()]

# Check existing
existing = conn.execute('SELECT COUNT(*) FROM daily_data WHERE date=?', (TARGET,)).fetchone()[0]
if existing >= 400:
    print(f"Already {existing} rows for {TARGET}, skip")
    conn.close()
    exit()

print(f"Downloading {TARGET} for {len(codes)} stocks...")

headers = {'Referer': 'https://finance.sina.com.cn'}
ok = fail = 0

for i, code in enumerate(codes):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen=1'
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data and len(data) > 0:
            row = data[-1]  # latest
            if row['day'] == TARGET:
                conn.execute('''INSERT OR REPLACE INTO daily_data 
                    (code, date, open, high, low, close, volume, amount)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (code, TARGET, float(row['open']), float(row['high']),
                     float(row['low']), float(row['close']), float(row['volume']), 0))
                ok += 1
            else:
                fail += 1
        else:
            fail += 1
    except Exception as e:
        fail += 1
    
    if (i+1) % 100 == 0:
        conn.commit()
        print(f"  {i+1}/{len(codes)} ok={ok} fail={fail}")
    time.sleep(0.08)

conn.commit()
print(f"\nDONE: ok={ok} fail={fail}")
conn.close()
