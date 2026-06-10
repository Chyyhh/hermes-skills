---
name: a-stock-database
description: 建立 A 股数据库 — 获取指数成分股、批量下载历史行情、SQLite 存储与数据完整性校验
category: data-science
---

# A-Stock Database — A 股数据库构建

用 akshare 建立本地 A 股日线数据库，支持指数成分股获取、批量并行下载、数据校验。

## 适用场景

- 中证 A500、沪深300、中证500 等指数的历史行情下载
- 量化回测数据准备
- 全市场扫描分析

## 工作流程

### 1️⃣ 获取指数成分股（⚠️ 数据源选择是关键坑）

**优先使用** `index_stock_cons_csindex()`（中证指数官网），**不要**用 `index_stock_cons()`（新浪）。

```python
import akshare as ak

# ✅ 正确：中证指数官网 — 数据干净，500只无重复
cons = ak.index_stock_cons_csindex(symbol="000510")  # 中证A500
# 返回列: ['日期', '指数代码', '指数名称', '成分券代码', '成分券名称', '交易所', ...]
# 唯一代码数 = 500 ✅

# ❌ 不要用这个：新浪财经对A500(000510)只返回371个唯一代码
# cons = ak.index_stock_cons(symbol="000510")  # BUG: 500行仅371只唯一！

# symbol: 000510=A500, 000300=沪深300, 000905=中证500, 000016=上证50
```

**为什么 `index_stock_cons()` 不行？**
同一只股票因历史调仓被重复计入，A500(000510) 返回500行数据但只有371个唯一股票代码。129只股票有重复行，`unique()` 会丢数据。

### 2️⃣ 判断交易所前缀

```python
def get_exchange(code):
    return 'sh' if code.startswith('6') else 'sz'
symbol = get_exchange(code) + code  # 例如 'sh600519'
```

### 3️⃣ 下载历史行情（⚠️ 首选腾讯API，akshare可能被限）

**首选方案：腾讯财经 HTTP/2 API**（快、稳定、无封IP风险）

```python
import requests

# 腾讯API：大盘股用 sh，中小盘用 sz
prefix = 'sh' if code.startswith('6') else 'sz'
url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,1,qfq'
r = requests.get(url, timeout=10)
data = r.json()
days = data['data'][f'{prefix}{code}'].get('qfqday', [])
# 每条: [date, open, close, high, low, volume(手)]
# volume需×100转为股
```

性能：**82秒/250只**（50ms间隔），成功率 **97%+**。完整脚本见 `scripts/download_a500.py`。

**备用方案：新浪财经 API**（容易被限流，仅作fallback）
```python
prefix = 'sh' if code.startswith('6') else 'sz'
url = f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen=1'
```
新浪无成交额(amount)字段，volume填入amount=0。

**⚠️ akshare 可能被封**：部分网络环境（如WSL）下，akshare依赖的东方财富API返回空响应（RemoteDisconnected）。此时必须切换腾讯或新浪API。

### 4️⃣ 批量并行下载

拆分任务为多批，用 `delegate_task` 并行：

```python
# 分3批，每批 ~167只
n = len(stocks)
batch_sz = (n + 2) // 3
for i in range(3):
    batch = stocks[i*batch_sz:(i+1)*batch_sz]
    # 每批约 3-5s/股 × 167 ≈ 8-14min
```

### 5️⃣ SQLite 建表

```sql
CREATE TABLE IF NOT EXISTS daily_data (
    code TEXT,
    date TEXT,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL, turnover REAL,
    PRIMARY KEY (code, date)
);
```

并发写入必须启用 WAL 模式：

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
```

## 关键陷阱

### ⚠️ 指数成分股重复
`index_stock_cons` 返回的 **行数 ≠ 唯一股票数**。因调仓再纳入，同一股票可能有多个 纳入日期 行。

```python
# 错误做法
for s in cons:  # 500 行但实际只有 371 只
# 正确做法
unique_codes = cons['品种代码'].unique()  # 先去重
```

### ⚠️ 停牌股票
部分股票（如建元信托 600816）可能长期停牌，数据有日期断档，属于正常现象。

### ⚠️ 新股/次新股
科创板（688xxx）股票可能不足5年历史，数据行数较少。

### ⚠️ akshare 请求限制与网络问题

**东方财富API可能被限**：部分环境（WSL、境外IP等）下，akshare依赖的东方财富API（push2his.eastmoney.com）返回空响应或 RemoteDisconnected。症状：curl可达但Python requests被拒。

**解决方案（按优先级）**：
1. 🥇 **腾讯财经API** — `web.ifzq.gtimg.cn`，HTTP/2，无封IP，82s/250只
2. 🥈 **新浪财经API** — `money.finance.sina.com.cn`，易被限流，~40%成功率
3. 🥉 **akshare** — 仅当上面两个都不可用时尝试

**限流对策**：
- 每个请求间隔 0.05-0.15s（腾讯API可0.05s，新浪需0.15s）
- 失败重试 3 次，间隔递增（1s/2s/3s）
- 每50只 commit 一次，每100只额外暂停1s
- 断点续传：先查已有记录，只下载缺失的

## 数据完整性检查

下载完毕后必须验证：

```python
# 1. 股票数匹配
cons = ak.index_stock_cons(symbol)
db_codes = set(cons['品种代码'].unique())
assert len(db_codes) == len(unique_akshare_codes)

# 2. 无空值
df.isnull().sum().sum() == 0

# 3. 价格范围合理
df['close'].between(0.1, 10000).all()

# 4. 无重复记录
df.duplicated(subset=['code','date']).sum() == 0

# 5. 交易日覆盖率
# 检查最近5个交易日大部分股票都有数据
```

## 并发下载模板

参考 `references/parallel-download.md` 获取完整脚本模板。腾讯API下载方案见 `references/tencent-api-download.md`。
