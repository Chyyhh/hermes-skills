---
name: crypto-sma-resonance
description: Multi-timeframe SMA共振分析 — 从 Gate.io/Binance 获取永续合约K线，计算7/28/84 SMA排列与方向，判定多头/空头共振信号
---

# Crypto SMA 多周期共振分析

基于三条 SMA（7/28/84）在 1m/5m/15m/1h 四个周期上的排列和三线方向，判断多空共振信号。

## 触发条件

- 用户要求分析 BTCUSDT（或其他币种）永续合约的多周期 SMA 共振
- 用户要求「共振分析」「SMA排列」「均线共振」
- 需要快速生成多周期技术指标报告

## 数据获取

### 方式一：curl -k + subprocess（首选，最可靠）✅

`curl -k` 跳过证书验证可绕过 GFW 的 TLS RST，是目前最可靠的方案：

```python
import subprocess, json

def curl_get(url, timeout=15):
    result = subprocess.run(
        ['curl', '-sk', '--max-time', str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5
    )
    return json.loads(result.stdout)
```

### 方式二：urllib（备选，GFW 加强时可能失效）⚠️

```python
import urllib.request, json, ssl

ctx = ssl.create_default_context()
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
})
with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
    data = json.loads(resp.read().decode())
```

### 方式三：ccxt（GFW 下几乎不可用）❌

```python
import ccxt
exchange = ccxt.gateio({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
ohlcv = exchange.fetch_ohlcv('BTC/USDT:USDT', timeframe='1m', limit=100)
```

实际脚本 `scripts/btc_analysis.py` 已内置 curl → urllib 自动降级。

## 指标计算

### SMA（简单移动平均）

不依赖 pandas，手写实现：

```python
def calc_sma(closes, period):
    sma = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        sma[i] = sum(closes[i - period + 1:i + 1]) / period
    return sma
```

取最近 100 根 K 线（确保 84 周期 SMA 有效）。

### 排列判断

比较最新一根 K 线上的三条 SMA：

| 条件 | 信号 | 代码 |
|------|------|------|
| 7MA > 28MA > 84MA | 🟢多头 | bull |
| 7MA < 28MA < 84MA | 🔴空头 | bear |
| 其他 | ⚪缠绕 | cross |

### 三线方向判断

比较当前 SMA 与前一根 K 线上的 SMA：

| 条件 | 信号 | 代码 |
|------|------|------|
| 三线全部升高 | ↑↑↑ | up |
| 三线全部降低 | ↓↓↓ | down |
| 其他 | — | mixed |

## 共振判断

### 多头共振极致
**同时满足以下所有条件**：
- 4 个周期全部 7MA > 28MA > 84MA（bull）
- 4 个周期三线和前K比全部同时升高（up）

→ 输出：🔥🔥🔥 多头共振极致！做多信号！

### 空头共振极致
**同时满足以下所有条件**：
- 4 个周期全部 7MA < 28MA < 84MA（bear）
- 4 个周期三线和前K比全部同时降低（down）

→ 输出：❄️❄️❄️ 空头共振极致！做空信号！

### 不满足以上任一条件
→ ⚪ 观望

## 输出格式

```
BTCUSDT 最新价: $XX,XXX.XX (±X.XX%)

周期        7MA       28MA       84MA    排列      三线
──────────────────────────────────────────────────────────
1m      XXXXX.XX   XXXXX.XX   XXXXX.XX   🟢/🔴/⚪   ↑↑↑/↓↓↓/—
5m      XXXXX.XX   XXXXX.XX   XXXXX.XX
15m     XXXXX.XX   XXXXX.XX   XXXXX.XX
1h      XXXXX.XX   XXXXX.XX   XXXXX.XX

结论: 🔥多头共振极致 / ❄️空头共振极致 / ⚪观望
```

附加：排列和三线的详细分解（各周期 code），以及数据时间戳。

## 注意事项

- 不预测价格，不给出主观建议，只输出数据和技术信号
- Gate.io 合约格式用下划线 `BTC_USDT`，非 ccxt 的 `BTC/USDT:USDT`
- 价格变化百分比使用 ticker 接口的 `change_percentage` 字段
- 输出时排列列宽需容纳中文字符（🟢多头 = 4 个显示宽度但字符数不同）
- 脚本参考：`scripts/btc_analysis.py`
- GFW 网络环境备忘录：`references/gateio-gfw-workaround.md`

## 陷阱

- **Python 3.11 及以下禁止 f-string 中使用反斜杠转义**。`f"{'\u5468\u671f':<6}"` 会报 `SyntaxError: f-string expression part cannot include a backslash`。解决：将 Unicode 字符串预定义为变量再引用：`PERIOD = '\u5468\u671f'; f"{PERIOD:<6}"`。
- **GFW 对快速连续出站连接敏感**：即使单次 `curl -k` 成功，连续快速发起 5 个 Gate.io API 请求（ticker + 4 个周期 K 线）也会触发 GFW 的 RST 阻断（curl 报 error 35，urllib 报 ConnectionResetError）。解决：(1) 每次 API 调用之间加 2-3 秒延迟；(2) 每个请求内置重试+退避（retry with backoff），不要 curl 失败立即 fallback 到 urllib（urllib 更易被阻）；(3) 逐个获取数据、存为临时文件，最后统一处理。`scripts/btc_analysis.py` 已内置此模式。
- ccxt 和 urllib 在中国大陆网络环境下均可能因 TLS/GFW 阻断而失败，但 `curl -k`（跳过证书验证）可稳定绕过。脚本 `scripts/btc_analysis.py` 内置 curl → urllib 自动降级。
- Gate.io futures 的 timestamp 单位是**秒**，需 ×1000 转为毫秒。
- 输出中的 emoji 排列（🟢多头/🔴空头/⚪缠绕）是组合显示，直接用字符串模板拼接即可。
