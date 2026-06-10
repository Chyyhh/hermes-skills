#!/usr/bin/env python3
"""下载A股日线数据到SQLite数据库，支持多实例并行写入（WAL模式）。"""
import json
import sys
import time
import sqlite3
import akshare as ak

if len(sys.argv) < 2:
    print("用法: python3 download_batch.py <batch_json_file>")
    sys.exit(1)

batch_file = sys.argv[1]
db_path = sys.argv[2] if len(sys.argv) > 2 else "/home/zhfuyi/astock_a500.db"

with open(batch_file) as f:
    stocks = json.load(f)

print(f"批次: {len(stocks)} 只股票，目标: {db_path}")

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
conn.commit()

success = 0
failed = []

for i, stock in enumerate(stocks):
    code = stock['品种代码']
    name = stock.get('品种名称', '?')
    symbol = stock.get('symbol', f"{'sh' if code.startswith('6') else 'sz'}{code}")

    try:
        df = ak.stock_zh_a_daily(
            symbol=symbol,
            start_date="20200101",
            end_date="20260609",
            adjust="qfq"
        )

        if df.empty:
            print(f"  [{i+1}/{len(stocks)}] ⚠️ {code} {name}: 无数据")
            failed.append((code, "empty"))
            continue

        records = [
            (code, str(r['date']),
             float(r['open']), float(r['high']), float(r['low']),
             float(r['close']), float(r['volume']),
             float(r['amount']), float(r['turnover']))
            for _, r in df.iterrows()
        ]

        for bstart in range(0, len(records), 100):
            batch = records[bstart:bstart+100]
            retries = 3
            while retries > 0:
                try:
                    conn.executemany(
                        """INSERT OR REPLACE INTO daily_data
                           (code, date, open, high, low, close, volume, amount, turnover)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", batch)
                    conn.commit()
                    break
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() and retries > 0:
                        time.sleep(2)
                        retries -= 1
                    else:
                        raise

        success += 1
        if (i + 1) % 20 == 0 or i == 0:
            print(f"  [{i+1}/{len(stocks)}] ✅ {code} {name}: {len(df)} 行")
    except Exception as e:
        print(f"  [{i+1}/{len(stocks)}] ❌ {code} {name}: {e}")
        failed.append((code, str(e)[:60]))

conn.close()
print(f"\n✅ 完成! 成功: {success}, 失败: {len(failed)}")
if failed:
    print(f"前10失败: {failed[:10]}")
