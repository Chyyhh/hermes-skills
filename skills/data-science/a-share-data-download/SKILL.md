---
name: a-share-data-download
description: 下载A股历史数据（日线/指数成分股），含数据源选择、批量并行下载、完整性校验
category: data-science
---

# A股历史数据下载 — 工作流

## 触发条件
用户要求下载股票历史数据、建立A股数据库、获取指数成分股行情。

## 步骤

### 1. 获取指数成分股（数据源选择）

**⚠️ 关键坑：数据源差异巨大**

| 数据源 | 函数 | 可靠性 | 说明 |
|--------|------|--------|------|
| **中证指数官网** | `ak.index_stock_cons_csindex(symbol="000510")` | ✅ **权威** | 返回500行×500唯一，含日期/交易所/中英文名 |
| 新浪财经 | `ak.index_stock_cons(symbol="000510")` | ⚠️ 有bug | 返回500行但仅371唯一（108只重复），同一天重复3次 |

**规则**：
- **优先使用** `index_stock_cons_csindex()` — 中证指数官网，数据干净
- **仅当**官网接口不可用时才用 `index_stock_cons()`，且必须做去重 `drop_duplicates(subset=['品种代码'])`

例：
```python
# ✅ 正确方式
official = ak.index_stock_cons_csindex(symbol="000510")
codes = set(official['成分券代码'].tolist())
# → 500 只，无重复

# ❌ 错误方式（会丢数据）
sina = ak.index_stock_cons(symbol="000510")
codes = set(sina['品种代码'].tolist())
# → 371 只！129只重复丢失
```

### 2. 数据源选择（日线下载）

**⚠️ akshare 在 WSL 环境下经常被东方财富 API 限流，推荐使用腾讯财经 API 作为主力。**

| 数据源 | API | 速度 | 成功率 | 适用 |
|--------|-----|------|--------|------|
| **腾讯财经 HTTP/2** ⭐ | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | ⚡ 82s/250只 | **97%** | 日线增量更新 |
| 新浪财经 | `money.finance.sina.com.cn/.../getKLineData` | 🐢 慢 | ~40% | 备用（严重限流） |
| akshare(东方财富) | `ak.stock_zh_a_hist()` | ❌ 全断 | 0% | WSL 环境不可用 |

**腾讯API格式：**
```
GET http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{limit},qfq
返回: {data: {sz000001: {qfqday: [[date, open, close, high, low, volume_手], ...]}}}
```
- 成交量单位为「手」，需 ×100 转为股
- 无成交额字段（amount=0）
- HTTP/2 协议，响应快，限流宽松
- 代码前缀：6开头→sh，0/3开头→sz

**生产级下载脚本：** `/home/zhfuyi/download_a500.py`
- 自动检测缺失日期，断点续传（跳过已有数据）
- 失败3次重试，50只/批 commit
- 用法：`python3 download_a500.py`（最新缺失）、`python3 download_a500.py --all`（全量补全）

### 3. 扫描前自动校验（重要模式）

`scan_a500_buy.py` 已内置：扫描前先检查 DB 最新日期是否覆盖到最近交易日，不足450条自动触发下载：

```python
db_latest = conn.execute('SELECT MAX(date) FROM daily_data').fetchone()[0]
target = latest_trading_day()  # 跳过周末
if db_latest < target or cnt < 450:
    subprocess.run(['python3', '-u', '/home/zhfuyi/download_a500.py'])
```

### 4. 创建 SQLite 数据库

```python
import sqlite3
conn = sqlite3.connect("astock.db")
conn.execute("PRAGMA journal_mode=WAL")  # 支持并发写入
conn.execute("PRAGMA busy_timeout=30000")

# 日线数据表
conn.execute("""
    CREATE TABLE IF NOT EXISTS daily_data (
        code TEXT,
        date TEXT,
        open REAL, high REAL, low REAL, close REAL,
        volume REAL, amount REAL, turnover REAL,
        PRIMARY KEY (code, date)
    )
""")
```

### 5. 下载脚本模板（akshare 备选）

将以下脚本保存为 `download_batch.py`：

```python
#!/usr/bin/env python3
"""批量下载A股历史数据到SQLite数据库（支持并行）"""
import json, sys, time, sqlite3, akshare as ak

batch_file = sys.argv[1]
db_path = "/path/to/astock.db"
with open(batch_file) as f:
    stocks = json.load(f)

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
conn.commit()

success = 0
failed = []
for i, stock in enumerate(stocks):
    code = stock['品种代码']
    name = stock['品种名称']
    symbol = f"{'sh' if code.startswith('6') else 'sz'}{code}"
    
    try:
        df = ak.stock_zh_a_daily(symbol=symbol, start_date="20200101",
                                 end_date="20260609", adjust="qfq")
        if df.empty:
            failed.append((code, "empty"))
            continue
        
        records = [(code, str(r['date']), float(r['open']), float(r['high']),
                    float(r['low']), float(r['close']), float(r['volume']),
                    float(r['amount']), float(r['turnover']))
                   for _, r in df.iterrows()]
        
        # 分批写入，避免事务过大
        for bstart in range(0, len(records), 100):
            batch = records[bstart:bstart+100]
            conn.executemany(
                """INSERT OR REPLACE INTO daily_data
                   (code, date, open, high, low, close, volume, amount, turnover)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", batch)
            conn.commit()
        success += 1
        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(stocks)}] ✅ {code} {name}: {len(df)} 行")
    except Exception as e:
        print(f"  [{i+1}/{len(stocks)}] ❌ {code} {name}: {e}")
        failed.append((code, str(e)[:60]))
conn.close()
```

### 6. 批量并行下载

```python
# 分3批，利用 delegate_task 并行（最多3个子任务）
N = len(missing_stocks)
batch_sz = (N + 2) // 3
batches = [missing_stocks[i*batch_sz:(i+1)*batch_sz] for i in range(3)]

for i, batch in enumerate(batches):
    with open(f"/tmp/batch_{i}.json", "w") as f:
        json.dump(batch, f, ensure_ascii=False)

# 用 delegate_task 启动3个并行任务
# 每个任务运行: python3 download_batch.py /tmp/batch_{i}.json
```

### 7. 数据完整性校验

```python
def verify(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT code) FROM daily_data")
    stocks = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM daily_data")
    rows = c.fetchone()[0]
    c.execute("SELECT MIN(date), MAX(date) FROM daily_data")
    min_d, max_d = c.fetchone()
    
    # 检查空值
    c.execute("SELECT COUNT(*) FROM daily_data WHERE close IS NULL OR close = 0")
    nulls = c.fetchone()[0]
    
    # 检查异常波动（涨跌>20%，正常A股最大±10%或±20%）
    c.execute("""
        SELECT COUNT(*) FROM daily_data d1
        JOIN daily_data d2 ON d1.code=d2.code 
            AND d1.date=date(d2.date, '+1 day')
        WHERE abs((d1.close - d2.close)/d2.close) > 0.20
    """)
    anomalies = c.fetchone()[0]
    
    return {
        "stocks": stocks, "rows": rows, "min_date": min_d, "max_date": max_d,
        "null_values": nulls, ">20%_swings": anomalies
    }
```

## 参考信息

本技能附带以下参考文件：
- `references/a500-session-record.md` — A500具体下载实录（数据源对比、排查过程、验证发现）
- `templates/download_batch.py` — 可复用的并行下载脚本模板

| 指数 | 代码 | 说明 |
|------|------|------|
| 中证A500 | 000510 | 500只，2024-09-23发布 |
| 沪深300 | 000300 | 300只 |
| 中证500 | 000905 | 500只 |
| 上证50 | 000016 | 50只 |

## 已知坑

1. **新浪成分股有重复** — `index_stock_cons("000510")` 返回500行但只有371唯一代码，108只股票在同一天出现2-3次。**不要用**。
2. **⚠️ WSL 下 akshare 东方财富 API 被限** — `stock_zh_a_hist()` / `stock_zh_a_daily()` 直连东方财富时返回 `RemoteDisconnected`。**主用腾讯API**（`download_a500.py`），新浪备选。
3. **⚠️ 股票代码混淆（重要！）** — 同一名称的股票可能在主板+科创/创业板双上市，代码不同=两家公司！
   | 易混名称 | 正确代码 | 错误代码 |
   |:--------|:--------|:--------|
   | 生益电子 | **688183** (科创板PCB) | ❌ 600183 生益科技(主板覆铜板) |
   | 宁德时代 | 300750 | ❌ 无其他代码 |
   | 任何科创板股票 | start with 688/300 | ❌ 同名的600xxx主板公司 |
   
   **规则**：科创板(688xxx)/创业板(300xxx)和主板(600xxx/000xxx)同名称不同代码是**两家公司**。分析前必须用股票名称反查确认代码。
4. **A股代码规则** — `6xxxxx`=沪市(sh), `0xxxxx`/`3xxxxx`=深市(sz), `8xxxxx`/`4xxxxx`=北交所(bj)
4. **次新股数据不足** — 上市不足5年的股票只有部分数据，属正常现象
5. **停牌股** — 长期停牌的股票可能最后一交易日早于当前日期
6. **并发写入** — 多个进程同时写SQLite时启用WAL模式 + busy_timeout，否则报 `database is locked`
7. **科创板前缀** — `688xxx` 同样是 `sh` 前缀
