"""
A500 Daily Data Downloader — Tencent Finance API
Fast, reliable, with retry + resume.
Usage: python3 download_a500.py           # download latest missing date
       python3 download_a500.py 20260609  # download specific date
       python3 download_a500.py --all     # check & fill all missing dates
"""
import sqlite3, requests, time, sys, json

DB = '/home/zhfuyi/astock_a500.db'
TIMEOUT = 10
BATCH_COMMIT = 50
SLEEP = 0.05  # 50ms between requests (20 req/s)

def get_codes():
    conn = sqlite3.connect(DB)
    codes = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_data ORDER BY code').fetchall()]
    conn.close()
    return codes

def get_missing_dates():
    """Return dates that don't have full 500-record coverage"""
    conn = sqlite3.connect(DB)
    dates = [r[0] for r in conn.execute(
        'SELECT date FROM daily_data GROUP BY date HAVING COUNT(*)<400 ORDER BY date DESC').fetchall()]
    conn.close()
    return dates

def download_date(target_date, codes):
    """Download one date's data for all codes via Tencent API"""
    conn = sqlite3.connect(DB)
    done = set(r[0] for r in conn.execute('SELECT code FROM daily_data WHERE date=?', (target_date,)).fetchall())
    todo = [(c, 'sh' if c.startswith('6') else 'sz') for c in codes if c not in done]
    
    if not todo:
        print(f"  {target_date}: already complete")
        conn.close()
        return 0
    
    print(f"  {target_date}: {len(todo)} to download...", end=' ', flush=True)
    ok = fail = 0
    t0 = time.time()
    
    for i, (code, prefix) in enumerate(todo):
        url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,1,qfq'
        success = False
        
        for retry in range(3):
            try:
                r = requests.get(url, timeout=TIMEOUT)
                data = r.json()
                days = data['data'][f'{prefix}{code}'].get('qfqday', [])
                if days and days[-1][0] == target_date:
                    d = days[-1]  # [date, open, close, high, low, volume]
                    vol = float(d[5]) * 100  # 手 → 股
                    conn.execute('''INSERT OR REPLACE INTO daily_data 
                        (code, date, open, high, low, close, volume, amount)
                        VALUES (?,?,?,?,?,?,?,?)''',
                        (code, target_date, float(d[1]), float(d[3]),
                         float(d[4]), float(d[2]), vol, 0))
                    ok += 1
                    success = True
                    break
            except:
                time.sleep(1)
        
        if not success:
            fail += 1
        
        if (i+1) % BATCH_COMMIT == 0:
            conn.commit()
            print('.', end='', flush=True)
        
        time.sleep(SLEEP)
    
    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f' ok={ok} fail={fail} ({elapsed:.0f}s)')
    return ok

if __name__ == '__main__':
    codes = get_codes()
    print(f"Database: {len(codes)} stocks")
    
    if '--all' in sys.argv:
        dates = get_missing_dates()
        print(f"Missing dates: {len(dates)}")
        for d in dates:
            download_date(d, codes)
    elif len(sys.argv) > 1 and sys.argv[1] != '--all':
        download_date(sys.argv[1], codes)
    else:
        # Default: download latest missing
        conn = sqlite3.connect(DB)
        latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
        counts = conn.execute('SELECT date, COUNT(*) FROM daily_data GROUP BY date ORDER BY date DESC LIMIT 3').fetchall()
        conn.close()
        
        for d, c in counts:
            if c < 400:
                print(f"Latest incomplete: {d} ({c}/500)")
                download_date(d, codes)
                break
        else:
            print(f"All recent dates complete. Latest: {latest}")
