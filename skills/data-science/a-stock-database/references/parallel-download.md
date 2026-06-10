# Parallel Download Template

用于批量下载 A 股数据的并行下载脚本模板。

## 下载脚本 (download_batch.py)

```python
#!/usr/bin/env python3
"""批量下载 A 股日线数据到 SQLite"""
import json, sys, time, sqlite3
import akshare as ak

batch_file = sys.argv[1]
db_path = "/home/zhfuyi/astock_a500.db"

with open(batch_file) as f:
    stocks = json.load(f)

# WAL 模式支持并发写入
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

success = 0
failed = []

for i, stock in enumerate(stocks):
    code = stock['品种代码']
    name = stock['品种名称']
    symbol = stock['symbol']  # e.g. sh600519
    
    try:
        df = ak.stock_zh_a_daily(symbol=symbol, start_date="20200101",
                                 end_date="20260609", adjust="qfq")
        if df.empty:
            failed.append((code, "empty"))
            continue
        
        records = []
        for _, row in df.iterrows():
            records.append((
                code, str(row['date']),
                float(row['open']), float(row['high']),
                float(row['low']), float(row['close']),
                float(row['volume']), float(row['amount']),
                float(row['turnover'])
            ))
        
        # 分批写入，避免事务过大
        for batch_start in range(0, len(records), 100):
            batch = records[batch_start:batch_start+100]
            conn.executemany(
                """INSERT OR REPLACE INTO daily_data
                   (code, date, open, high, low, close, volume, amount, turnover)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", batch)
            conn.commit()
        
        success += 1
        if (i+1) % 20 == 0:
            print(f"[{i+1}/{len(stocks)}] {code} {name}: {len(df)} rows")
    except Exception as e:
        print(f"[{i+1}/{len(stocks)}] FAIL {code} {name}: {e}")
        failed.append((code, str(e)[:60]))

conn.close()
print(f"\nDone: {success} ok, {len(failed)} failed")
```

## 并行调度方式

在 Hermes 中通过 `delegate_task` 启动多个并行下载：

```python
# 分3批，每批写到同一个 DB (WAL 模式允许并发)
tasks = [
    {"goal": f"下载批次{i}", "context": f"运行: python3 download_batch.py batch_{i}.json",
     "toolsets": ["terminal"]}
    for i in range(3)
]
# 使用 delegate_task 并行执行
```

## 数据验证脚本

```python
import sqlite3, akshare as ak

conn = sqlite3.connect("astock_a500.db")
c = conn.cursor()

# 股票数
c.execute("SELECT COUNT(DISTINCT code) FROM daily_data")
print(f"Stocks: {c.fetchone()[0]}")

# 行数
c.execute("SELECT COUNT(*) FROM daily_data")
print(f"Rows: {c.fetchone()[0]:,}")

# 数据范围
c.execute("SELECT MIN(date), MAX(date) FROM daily_data")
print(f"Range: {c.fetchone()}")

# 每只股票最小行数 (检查停牌/次新股)
c.execute("SELECT code, COUNT(*) FROM daily_data GROUP BY code ORDER BY COUNT(*) LIMIT 10")
for code, cnt in c.fetchall():
    print(f"  {code}: {cnt} rows (low)")

# 空值检查
c.execute("""
    SELECT COUNT(*) FROM daily_data
    WHERE open IS NULL OR high IS NULL OR low IS NULL
       OR close IS NULL OR volume IS NULL
""")
print(f"Null values: {c.fetchone()[0]}")

# 重复检查
c.execute("""
    SELECT COUNT(*) - COUNT(DISTINCT code || date) FROM daily_data
""")
print(f"Duplicates: {c.fetchone()[0]}")

conn.close()
```

## akshare 常用股票指数代码

| 指数名称 | symbol |
|:--------|:------:|
| 中证 A500 | 000510 |
| 沪深 300 | 000300 |
| 中证 500 | 000905 |
| 上证 50 | 000016 |
| 创业板指 | 399006 |
| 科创 50 | 000688 |
