---
name: china-stock-data
description: 中国A股数据获取 — akshare 数据源、指数成分股、SQLite 数据库管理、每日数据更新
category: data-science
---

# China Stock Data — A股数据获取与数据库管理

## 数据源选择

### 指数成分股获取

| 数据源 | 方法 | 可靠性 | 说明 |
|:------|:----:|:------:|:------|
| **中证指数官网** ⭐ | `ak.index_stock_cons_csindex()` | ✅ **500只完整** | 官方数据，**优先使用** |
| 新浪财经 | `ak.index_stock_cons()` | ⚠️ 可能有重复 | 有时只返回部分股票 |

**关键陷阱：** `ak.index_stock_cons(symbol="000510")` 对中证A500指数可能只返回 **371只唯一股票**（500行中有129行是重复的历史调仓记录）。始终使用 `index_stock_cons_csindex()` 获取官方数据。

### 个股行情数据

**主力方案（推荐）**：腾讯财经 HTTP/2 API ~ 参见 `a-share-data-download` 技能。
生产脚本：`/home/zhfuyi/download_a500.py` — 82秒/250只，97%成功率，断点续传。

**备选方案**：akshare（WSL 环境东方财富API常被限流）

```python
import akshare as ak

# 日线数据（前复权）— WSL 下可能报 RemoteDisconnected
df = ak.stock_zh_a_daily(symbol='sh600519', start_date='20200101',
                          end_date='20260609', adjust='qfq')
```

**代码前缀规则：**
- `6`开头 → `sh`（上海主板/科创板）
- `0`开头 → `sz`（深圳主板）
- `3`开头 → `sz`（创业板）
- `4`/`8`开头 → `bj`（北交所）

## SQLite 数据库管理

### 建表

```sql
CREATE TABLE IF NOT EXISTS daily_data (
    code TEXT,           -- 股票代码（纯数字，无前缀）
    date TEXT,           -- 日期 YYYY-MM-DD
    open REAL, high REAL, low REAL, close REAL,
    volume REAL,         -- 成交量（股）
    amount REAL,         -- 成交额（元）
    turnover REAL,       -- 换手率
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    code TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,
    added_date TEXT
);
```

### 批量下载脚本

**核心脚本：** `download_batch.py`

```python
# 启用WAL模式支持并发写入
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

# 每100条批量写入，失败重试3次
for batch_start in range(0, len(records), 100):
    batch = records[batch_start:batch_start+100]
    conn.executemany("INSERT OR REPLACE INTO daily_data ...", batch)
    conn.commit()
```

### 并行下载

将500只股票分成3批并行下载（通过 delegate_task），每批约167只。
每只股票下载约3-5秒，3批并行约15-20分钟完成全市场。

## 每日更新（Cron Job）

### 收盘后自动更新脚本

位置：`~/.hermes/scripts/a500_daily_scan.py`

运行逻辑：
1. 扫描A500全部500只，补全未包含最新交易日的股票
2. 日期从 `SELECT MAX(date) FROM daily_data` 下一天开始
3. 运行3L选股扫描（缩量回踩 + 趋势突破 + 动量主线）
4. 生成报告发到聊天

### Cron 配置

```bash
# 每天收盘后运行（周一至周五）
cronjob action=create schedule="0 15 * * 1-5" \
    script="~/.hermes/scripts/a500_daily_scan.py" \
    no_agent=true
```

## 数据验证

```sql
-- 检查完整性：应有500只
SELECT COUNT(DISTINCT code) FROM daily_data;

-- 最新交易日覆盖
SELECT code, MAX(date) FROM daily_data 
GROUP BY code ORDER BY MAX(date) LIMIT 5;

-- 数据范围
SELECT MIN(date), MAX(date) FROM daily_data;

-- 异常值检查
SELECT COUNT(*) FROM daily_data 
WHERE close <= 0 OR volume <= 0;
```

## 性能优化

- WAL模式：并发写入不阻塞读取
- 索引：`CREATE INDEX idx_date ON daily_data(date)`
- 每100条 batch 写入，避免大事务
- 下载时用前复权 `adjust='qfq'`
