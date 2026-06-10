#!/usr/bin/env python3
"""
3L体系 K线图生成器 — 生成带买卖点标注的K线图

用法:
  python3 plot_3l_chart.py <股票代码> [--start 2026-01-01] [--end 2026-06-09]

示例:
  python3 plot_3l_chart.py 603986                   # 兆易创新近3月
  python3 plot_3l_chart.py 688183 --start 2026-01-01 # 生益电子年初至今
  python3 plot_3l_chart.py 600941 --year             # 中国移动近1年
"""
import sys
sys.dont_write_bytecode = True

import akshare as ak
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import argparse
from datetime import datetime, timedelta

# ========== 中文字体设置 ==========
_FONT_TTC = '/home/zhfuyi/.local/share/fonts/NotoSansCJK-Regular.ttc'
if True:
    try:
        fm.fontManager.addfont(_FONT_TTC)
        plt.rcParams['font.family'] = 'Noto Sans CJK JP'
        plt.rcParams['axes.unicode_minus'] = False
    except Exception:
        pass  # 回退到无中文（英文标注）

# ========== 默认参数 ==========
DARK_BG = '#1a1a2e'
GRID_COLOR = '#2a2a4a'
GREEN = '#00e676'
RED = '#ef5350'
GOLD = '#ffd700'
PURPLE = '#e040fb'
BLUE = '#448aff'

def get_code_with_prefix(code):
    code = code.strip()
    if code.startswith(('6', '9')):
        return 'sh' + code
    elif code.startswith(('0', '3')):
        return 'sz' + code
    elif code.startswith(('4', '8')):
        return 'bj' + code
    return code

def fetch_data(symbol, start_date, end_date):
    df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_date,
                              end_date=end_date, adjust='qfq')
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    return df

def add_indicators(df):
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma5']
    return df

def find_buy_zone(df):
    """找到最近的缩量回踩买点区域"""
    recent = df.tail(20)
    buy_start = None
    buy_end = None
    hi_15d = df['close'].tail(15).max()
    
    for i in range(len(recent)-1, -1, -1):
        row = recent.iloc[i]
        retrace = (row['close'] / hi_15d - 1) * 100
        near_ma20_pct = (row['close'] / row['MA20'] - 1) * 100
        
        if (row['vol_ratio'] < 0.85 and 
            row['MA5'] > row['MA20'] > row['MA60'] and
            -15 < retrace < -2 and
            -3 < near_ma20_pct < 10):
            if buy_end is None:
                buy_end = row.name
            buy_start = row.name
    
    return buy_start, buy_end

def find_sell_points(df):
    """找到近期的卖出信号点 — SELL标记用于K线图"""
    points = []
    data = df.copy()
    n = len(data)
    if n < 20:
        return points
    
    # SELL ①: 冲高远离MA20（放量滞涨）
    for i in range(max(5, n-90), n-3, 1):
        row = data.iloc[i]
        vol_ratio = row['volume'] / max(data.iloc[max(0,i-5):i+1]['volume'].mean(), 1)
        dist_ma20 = (row['close'] / row['MA20'] - 1) * 100
        if dist_ma20 > 12 and vol_ratio > 1.3:
            hi = row['close']
            future = data.iloc[i:i+5]['close']
            if len(future) > 0 and future.max() <= hi * 1.02:
                points.append((row.name, row['close'], 'SELL', dist_ma20))
    
    # 取最多3个最有代表性的卖点
    if points:
        points.sort(key=lambda x: -x[2]) if points else points.sort(key=lambda x: -x[3])
        points = points[:3]
        for idx, p in enumerate(points):
            points[points.index(p)] = (p[0], p[1], f'SELL {idx+1}', p[3])
    return points

def plot_chart(df, code, name=""):
    """生成带买卖点标注的K线图"""
    if len(df) < 10:
        print(f"❌ {code}: 数据不足")
        return None
    
    # 深色主题
    mc = mpf.make_marketcolors(up=RED, down='#26a69a',
                                edge='inherit', wick='inherit',
                                volume='#ced4da')
    s = mpf.make_mpf_style(marketcolors=mc, facecolor=DARK_BG,
                            figcolor=DARK_BG, gridcolor=GRID_COLOR,
                            gridstyle='--')
    
    apds = [
        mpf.make_addplot(df['MA5'], color=GOLD, width=0.8),
        mpf.make_addplot(df['MA10'], color=PURPLE, width=0.8),
        mpf.make_addplot(df['MA20'], color=GREEN, width=1.0),
        mpf.make_addplot(df['MA60'], color=BLUE, width=0.8),
        mpf.make_addplot(df['vol_ratio'], panel=2, color=GOLD,
                          width=0.6, ylabel='量比'),
    ]
    
    fig, axes = mpf.plot(df, type='candle', style=s, volume=True,
                          addplot=apds, figsize=(16, 10),
                          panel_ratios=(3, 1, 0.8),
                          returnfig=True, tight_layout=True,
                          xrotation=15, datetime_format='%m/%d')
    
    ax_main = axes[0]
    ax_vol = axes[2]
    
    # 找买点区域
    buy_start, buy_end = find_buy_zone(df)
    if buy_start and buy_end:
        ax_main.axvspan(buy_start, buy_end, alpha=0.18,
                         color=GREEN, zorder=5)
        mid_price = df.loc[buy_end, 'close'] if buy_end in df.index else df.iloc[-1]['close']
        ax_main.annotate(f'BUY ZONE\\n缩量回踩MA20\\n¥{mid_price:.1f}',
                          xy=(buy_end, min(mid_price * 1.05, df['high'].max())),
                          xytext=(buy_start, df['high'].max() * 1.08),
                          fontsize=14, fontweight='bold', color=GREEN,
                          bbox=dict(boxstyle='round', facecolor=DARK_BG,
                                    edgecolor=GREEN, alpha=0.9),
                          arrowprops=dict(arrowstyle='->', color=GREEN, lw=2),
                          zorder=10)
    
    # 卖点标注 — SELL ① ② ③
    sell_points = find_sell_points(df)
    if sell_points and 'high' in df.columns:
        y_max = df['high'].max()
        for dt, price, label, dist in sell_points:
            if dt in df.index:
                y_loc = min(price * 1.06, y_max * 0.98)
                ax_main.annotate(f'{label}\\n¥{price:.0f}',
                                  xy=(dt, price),
                                  xytext=(dt, y_loc),
                                  fontsize=11, fontweight='bold', color=RED,
                                  bbox=dict(boxstyle='round', facecolor=DARK_BG,
                                            edgecolor=RED, alpha=0.85),
                                  arrowprops=dict(arrowstyle='->', color=RED, lw=2),
                                  zorder=10)
    
    # 前高卖压区
    hi_idx = df['close'].idxmax()
    if hi_idx in df.index[:-5]:
        ax_main.axvspan(hi_idx, df.index[-1], alpha=0.1, color=RED, zorder=5)
    
    # MA20标注
    last = df.iloc[-1]
    ax_main.annotate(f'MA20=¥{last["MA20"]:.0f}\\n关键支撑',
                      xy=(df.index[-1], last['MA20']),
                      fontsize=11, color=GREEN,
                      bbox=dict(boxstyle='round', facecolor=DARK_BG,
                                edgecolor=GREEN, alpha=0.8),
                      zorder=10)
    
    title = f'{code} {name} — 3L体系买卖点分析' if name else f'{code} — 3L体系买卖点分析'
    ax_main.set_title(title, fontsize=18, fontweight='bold',
                       color='white', pad=15)
    
    # 量比
    ax_vol.axhline(y=0.8, color=GOLD, linestyle='--', linewidth=0.8, alpha=0.6)
    ax_vol.text(0.02, 0.9, '量比<0.8=缩量', transform=ax_vol.transAxes,
                fontsize=10, color=GOLD, verticalalignment='top')
    
    output = f'/home/zhfuyi/3l_chart_{code}.png'
    fig.savefig(output, dpi=150, bbox_inches='tight', facecolor=DARK_BG)
    plt.close()
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='3L体系 K线图生成')
    parser.add_argument('code', help='股票代码, e.g. 603986')
    parser.add_argument('--name', default='', help='股票名称')
    parser.add_argument('--start', default=None, help='开始日期 YYYYMMDD')
    parser.add_argument('--end', default=None, help='结束日期 YYYYMMDD')
    parser.add_argument('--year', action='store_true', help='近1年数据')
    args = parser.parse_args()
    
    end = args.end or datetime.now().strftime('%Y%m%d')
    if args.year:
        start = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
    elif args.start:
        start = args.start
    else:
        start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    
    symbol = get_code_with_prefix(args.code)
    print(f"获取 {args.code} 数据: {start} ~ {end}...")
    df = fetch_data(symbol, start.replace('-', ''), end.replace('-', ''))
    df = add_indicators(df)
    df = df.dropna()
    
    output = plot_chart(df, args.code, args.name)
    if output:
        print(f"✅ 图表已保存: {output}")
    else:
        sys.exit(1)
