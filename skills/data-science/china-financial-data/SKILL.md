---
name: china-financial-data
description: 中国A股金融数据工作流 — 使用 akshare 获取分股/指数数据，SQLite 存储，数据完整性校验
category: data-science
---

# China Financial Data Workflow

使用 akshare 获取中国A股数据，SQLite 存储，数据质量保障。

## 主要数据源

### 指数成分股 — 用中证官网接口
```python
# ✅ 正确：中证指数官网（无重复数据 500/500）
df = ak.index_stock_cons_csindex(symbol="000510")

# ❌ 错误：新浪财经（有重复代码，A500 只返回 371 只）
df = ak.index_stock_cons(symbol="000510")
```

**陷阱**：`ak.index_stock_cons()` 对 A500(000510) 返回 500 行但仅 371 个唯一代码（同只股票因多次调仓重复计入）。**必须用 `index_stock_cons_csindex()`** 从中证官网获取准确名单。

### A股日线数据
```python
df = ak.stock_zh_a_daily(symbol="sh600519", start_date="20200101",
                         end_date="20260609", adjust="qfq")
# symbol 格式: sh600519 (沪市sh, 深市sz, 北交所bj)
# adjust: qfq=前复权, hfq=后复权, 空=不复权
```

### 判断交易所前缀
```python
def get_exchange(code):
    if code.startswith('6'):
        return 'sh'   # 上海主板 + 科创板
    return 'sz'       # 深圳主板 + 创业板
```

## SQLite 存储模式

### 建表
```python
conn = sqlite3.connect("/path/to/db")
conn.execute("PRAGMA journal_mode=WAL")  # 支持并发读写
conn.execute("PRAGMA busy_timeout=30000")

c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS daily_data (
        code TEXT,
        date TEXT,
        open REAL, high REAL, low REAL, close REAL,
        volume REAL, amount REAL, turnover REAL,
        PRIMARY KEY (code, date)
    )
""")
c.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_data(date)")
```

### 批量写入（含重试机制）
```python
# 分批写入防事务过大
for batch_start in range(0, len(records), 100):
    batch = records[batch_start:batch_start+100]
    retries = 3
    while retries > 0:
        try:
            conn.executemany("INSERT OR REPLACE INTO daily_data ...", batch)
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and retries > 0:
                time.sleep(2)
                retries -= 1
            else:
                raise
```

## 数据完整性检查

下载完成后必须验证：

```python
c.execute("SELECT COUNT(DISTINCT code) FROM daily_data")
c.execute("SELECT COUNT(*) FROM daily_data")
c.execute("SELECT MIN(date), MAX(date) FROM daily_data")

# 检查字段完整性
c.execute("""
    SELECT COUNT(*) FROM daily_data
    WHERE open IS NULL OR close IS NULL OR volume IS NULL
""")
assert rows[0] == 0, "有空值！"

# 检查价格合理性
c.execute("""
    SELECT COUNT(*) FROM daily_data 
    WHERE close <= 0 OR open <= 0 OR high < low
""")
assert rows[0] == 0, "有异常价格！"

# 数据去重检查
c.execute("""
    SELECT code, date, COUNT(*) as cnt FROM daily_data
    GROUP BY code, date HAVING cnt > 1
""")
assert len(rows) == 0, "有重复记录！"
```

## 常见问题

| 问题 | 原因 | 解决 |
|:----|:----|:-----|
| 指数成分股数少于预期 | 用错了API | 改用 `index_stock_cons_csindex()` |
| 次新股数据不足5年 | 上市时间短 | 正常现象，数据量就是实际交易日数 |
| 股票某天无数据 | 停牌/涨停/跌停 | 检查是否为停牌期，正常 |
| 某只股票数据特别少 | 长期停牌 | 如 600816 建元信托曾停牌数年 |
| SQLite 写入冲突 | 多进程并发 | 启用 WAL 模式 + busy_timeout |

## 回放检查清单

1. ✅ 确认使用正确的 akshare API（优先中证官网接口）
2. ✅ 检查唯一股票数是否与官方一致
3. ✅ 确认数据时间范围符合预期（如 5年）
4. ✅ 检查空值、零值、价格异常
5. ✅ 检查重复记录
6. ✅ 检查次新股/停牌股的特殊情况
