#!/usr/bin/env python3
"""BTCUSDT perpetual SMA multi-timeframe resonance analysis.
Uses curl -k (insecure) as primary transport to bypass GFW TLS RST.
Falls back to urllib if curl is unavailable.

Usage:
    python3 btc_analysis.py                     # BTCUSDT default
    python3 btc_analysis.py ETH_USDT            # custom contract
"""

import json
import subprocess
import sys
import time

TIMEFRAMES = ['1m', '5m', '15m', '1h']
LIMIT = 100
SMA_PERIODS = [7, 28, 84]


def api_get_curl(url, timeout=15):
    """Primary: fetch JSON via curl -k (bypasses GFW TLS RST)."""
    result = subprocess.run(
        ['curl', '-sk', '--max-time', str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5
    )
    if result.returncode != 0:
        raise Exception(f"curl failed ({result.returncode}): {result.stderr[:200]}")
    return json.loads(result.stdout)


def api_get_urllib(url, timeout=15):
    """Fallback: fetch JSON via urllib (may fail under GFW)."""
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode())


def api_get(url, timeout=15, retries=3, delay=2):
    """Fetch JSON from Gate.io API — curl -k with retry+backoff, urllib fallback."""
    # curl with retry + exponential backoff first (GFW triggers on rapid bursts)
    for attempt in range(retries):
        try:
            return api_get_curl(url, timeout)
        except Exception as e_curl:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            # curl exhausted — try urllib once as last resort
            try:
                return api_get_urllib(url, timeout)
            except Exception as e_url:
                raise Exception(
                    f"Both transports failed.\n"
                    f"  curl: {str(e_curl)[:150]}\n"
                    f"  urllib: {str(e_url)[:150]}"
                )


def fetch_klines(contract, interval, limit):
    """Fetch candlestick data from Gate.io futures USDT market."""
    url = (
        "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
        f"?contract={contract}&interval={interval}&limit={limit}"
    )
    data = api_get(url)
    if data is None:
        return None
    ohlcv = []
    for candle in data:
        ts = int(candle['t']) * 1000  # seconds → ms
        o = float(candle['o'])
        h = float(candle['h'])
        l = float(candle['l'])
        c = float(candle['c'])
        v = float(candle['v'])
        ohlcv.append([ts, o, h, l, c, v])
    return ohlcv


def fetch_ticker(contract):
    """Fetch ticker for percentage change and latest price."""
    url = f"https://api.gateio.ws/api/v4/futures/usdt/tickers?contract={contract}"
    data = api_get(url)
    if data and len(data) > 0:
        t = data[0]
        return {
            'last': float(t.get('last', 0)),
            'change_percentage': float(t.get('change_percentage', 0)),
        }
    return None


def calc_sma(closes, period):
    """Calculate SMA for given period. Returns list with None for pre-SMA indices."""
    n = len(closes)
    sma = [None] * n
    for i in range(period - 1, n):
        sma[i] = sum(closes[i - period + 1:i + 1]) / period
    return sma


def main():
    contract = sys.argv[1] if len(sys.argv) > 1 else 'BTC_USDT'

    ticker = fetch_ticker(contract)
    if ticker:
        latest_price = ticker['last']
        change_pct = ticker['change_percentage']
    else:
        latest_price = None
        change_pct = None

    results = {}
    for tf in TIMEFRAMES:
        ohlcv = fetch_klines(contract, tf, LIMIT)
        if ohlcv is None:
            print(f"ERROR: Failed to fetch {tf} klines", file=sys.stderr)
            sys.exit(1)
        closes = [c[4] for c in ohlcv]
        smas = {}
        for p in SMA_PERIODS:
            smas[p] = calc_sma(closes, p)
        results[tf] = {
            'closes': closes,
            'smas': smas,
            'latest_close': closes[-1],
        }
        # Pace requests to avoid GFW RST on rapid successive outbound connections
        if tf != TIMEFRAMES[-1]:
            time.sleep(2)

    if latest_price is None:
        latest_price = results['1h']['latest_close']

    # Per-timeframe analysis
    tf_reports = []
    for tf in TIMEFRAMES:
        r = results[tf]
        ma7_now = r['smas'][7][-1]
        ma28_now = r['smas'][28][-1]
        ma84_now = r['smas'][84][-1]
        ma7_prev = r['smas'][7][-2]
        ma28_prev = r['smas'][28][-2]
        ma84_prev = r['smas'][84][-2]

        if ma7_now > ma28_now > ma84_now:
            alignment, align_code = '🟢多头', 'bull'
        elif ma7_now < ma28_now < ma84_now:
            alignment, align_code = '🔴空头', 'bear'
        else:
            alignment, align_code = '⚪缠绕', 'cross'

        dir7 = ma7_now - ma7_prev
        dir28 = ma28_now - ma28_prev
        dir84 = ma84_now - ma84_prev

        if dir7 > 0 and dir28 > 0 and dir84 > 0:
            direction, dir_code = '↑↑↑', 'up'
        elif dir7 < 0 and dir28 < 0 and dir84 < 0:
            direction, dir_code = '↓↓↓', 'down'
        else:
            direction, dir_code = '—', 'mixed'

        tf_reports.append({
            'tf': tf, 'ma7': ma7_now, 'ma28': ma28_now, 'ma84': ma84_now,
            'alignment': alignment, 'align_code': align_code,
            'direction': direction, 'dir_code': dir_code,
        })

    # Build output
    out = []
    if change_pct is not None:
        out.append(f"{contract.replace('_', '')} 最新价: ${latest_price:,.2f} ({change_pct:+.2f}%)")
    else:
        out.append(f"{contract.replace('_', '')} 最新价: ${latest_price:,.2f}")

    out.append("")
    out.append(f"{'周期':<6} {'7MA':>10} {'28MA':>10} {'84MA':>10} {'排列':<8} {'三线'}")
    out.append("─" * 58)

    for r in tf_reports:
        out.append(
            f"{r['tf']:<6} {r['ma7']:>10,.2f} {r['ma28']:>10,.2f} {r['ma84']:>10,.2f} "
            f"{r['alignment']:<8} {r['direction']}"
        )

    out.append("")

    # Resonance check
    all_bull = all(r['align_code'] == 'bull' for r in tf_reports)
    all_bear = all(r['align_code'] == 'bear' for r in tf_reports)
    all_up = all(r['dir_code'] == 'up' for r in tf_reports)
    all_down = all(r['dir_code'] == 'down' for r in tf_reports)

    if all_bull and all_up:
        out.append("结论: 🔥🔥🔥 多头共振极致！做多信号！")
    elif all_bear and all_down:
        out.append("结论: ❄️❄️❄️ 空头共振极致！做空信号！")
    else:
        out.append("结论: ⚪ 观望")

    align_detail = ' | '.join(f'{r["tf"]}={r["align_code"]}' for r in tf_reports)
    dir_detail = ' | '.join(f'{r["tf"]}={r["dir_code"]}' for r in tf_reports)
    out.append("")
    out.append(f"排列: {align_detail}")
    out.append(f"三线: {dir_detail}")

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    out.append(f"时间: {now_utc}")

    print("\n".join(out))


if __name__ == '__main__':
    main()
