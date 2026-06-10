# Gate.io API v4 — GFW 环境访问备忘录

## 背景

在中国大陆网络环境（GFW）下，`ccxt` 库（底层用 `requests`）连接主流交易所 API 全部超时或连接重置。此外 `urllib.request` 和普通 `curl` 也可能因 TLS 握手阶段被 GFW 的 TCP RST 阻断（`Connection reset by peer` / `Recv failure`）。

原因推测：GFW 对 TLS SNI 进行深度包检测，在 Client Finished 后发送 RST。

## 解决方案（按可靠性排序）

### 方案一：`curl -k`（最可靠）✅

`curl -k`（`--insecure`，跳过证书验证）可绕过 GFW 的 TLS 检测：

```bash
curl -sk --max-time 15 "https://api.gateio.ws/api/v4/futures/usdt/tickers?contract=BTC_USDT"
```

在 Python 中通过 `subprocess` 调用：

```python
import subprocess, json

def curl_get(url, timeout=15):
    result = subprocess.run(
        ['curl', '-sk', '--max-time', str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5
    )
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr[:200]}")
    return json.loads(result.stdout)
```

### 方案二：`urllib.request`（有时可用，不可靠）⚠️

Python 标准库 `urllib.request` 在部分时段/网络下可直连，但在 GFW 加强时也会被阻断（`ConnectionResetError: [Errno 104]`）。不推荐作为唯一方案。

### 方案三：`curl` 普通模式（不可靠）❌

不带 `-k` 的 `curl` 同样会被 GFW RST，与 `urllib` 表现一致。

已验证可用的端点：
- K线: `https://api.gateio.ws/api/v4/futures/usdt/candlesticks`
- Ticker: `https://api.gateio.ws/api/v4/futures/usdt/tickers`
- 服务器时间: `https://api.gateio.ws/api/v4/spot/time`

## 不要做的

- ❌ 不要逐个尝试不同交易所（Binance/OKX/Bybit/MEXC）——它们全部超时，浪费时间
- ❌ 不要用 `verify=False` 或自定义 SSL context 尝试修复 ccxt/urllib——问题不在证书验证而在 TLS 握手阶段的 GFW RST
- ❌ 不要假设 `urllib` 始终可用——它在 GFW 收紧时会失效，优先用 `curl -k`
