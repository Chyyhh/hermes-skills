---
name: jianfang-3l-trading-model
description: 交易者简放（焦峰）的3L交易体系 — 动量主线+最强逻辑+量价择时
category: mlops
---

# 交易者简放 3L 交易模型

## 简介

交易者简放（本名焦峰）的 **3L 交易体系**，基于其微博(jianfang78)、著作《交易至"简"》和公开访谈整理。

**核心: 3L**
1. **动量主线** — 跟随市场选择的主线板块
2. **最强逻辑** — 选产业/业绩/资金逻辑最强的个股
3. **量价择时** — 用成交量和价格关系确定买卖时机

## 文件位置

完整模型: `/home/zhfuyi/交易者简放_交易模型.md`

## 量化选股脚本

| 文件 | 说明 |
|:----|:------|
| `scripts/pullback_scanner.py` | 缩量回踩选股器 — 基于3L体系的量化扫描 |
| `scripts/backtest_3l.py` | 回测引擎 — 单只股票或全市场回测 |
| `scripts/plot_3l_chart.py` | **K线图生成器** — 带买卖点区域标注的可视化图表 |

### K线图可视化
```bash
# 生成兆易创新 K线图（带买点标注）
python3 scripts/plot_3l_chart.py 603986

# 指定股票名称和区间
python3 scripts/plot_3l_chart.py 688183 --name "生益电子" --start 2026-01-01

# 近1年数据
python3 scripts/plot_3l_chart.py 600941 --year
```

输出为 `/home/zhfuyi/3l_chart_{code}.png`，可用 MEDIA: 路径直接发送到飞书。

### 用法
```bash
python3 /home/zhfuyi/.hermes/skills/mlops/jianfang-3l-trading-model/scripts/pullback_scanner.py
```

### 选股逻辑（量化版）
```python
条件 = (
    均线多头(MA5 > MA20 > MA60) &
    回撤2%-15%(从近15日高点) &
    缩量(当日量 < 20日均量×0.8) &
    仍处于10日/20日上涨趋势 &
    仍在60日均线上方
)
# 最优信号: 股价接近MA20 (±3%) + 缩量最明显
```

## 回测引擎

完整回测脚本: `scripts/backtest_3l.py`

### 单只股票回测
```bash
python3 scripts/backtest_3l.py --code 600183 --start 2023-06-01
```

输出: 全部买卖信号按时间排列，含价格和信号类型。

### 全市场扫描
```bash
python3 scripts/backtest_3l.py --scan --threshold 0.8
```

输出:
- 缩量回踩买点（按分数排序，最高3星）
- 放量突破信号（量比>1.5）

### 信号规则
详细规则见 `references/trading-signals.md`

| 买入信号 | 卖出信号 |
|:---------|:---------|
| BUY_突破 (放量>1.5+新高) | SELL_跌破MA20 |
| BUY_回踩 (缩量<0.85+近MA20) | SELL_放量滞涨 (天量>2.0) |
| BUY_多头启动 (多头刚形成) | SELL_死叉 (MA5<MA10) |

## 每日收盘扫描 (Cron Job)

在飞书对话中已配置的 cron job 每天15:00执行:
- 更新A500全市场数据
- 运行全市场扫描 (缩量回踩 + 放量突破)
- 识别当前动量主线板块
- 自动投递分析报告

## 📉 K线图可视化（买卖点标注）

用户偏好 **K线图 + 买卖点区域标注**，而非纯文本表格。用 `mplfinance` 生成：

```python
import akshare as ak, pandas as pd, mplfinance as mpf

df = ak.stock_zh_a_daily(symbol='sh603986', start_date='...', adjust='qfq')
df['date'] = pd.to_datetime(df['date']); df.set_index('date', inplace=True)
df['MA20'] = df['close'].rolling(20).mean()

# 深色主题
mc = mpf.make_marketcolors(up='#ef5350', down='#26a69a', ...)
s = mpf.make_mpf_style(marketcolors=mc, facecolor='#1a1a2e', ...)

apds = [mpf.make_addplot(df['MA20'], color='#00e676', width=1.0)]
fig, axes = mpf.plot(df, type='candle', style=s, volume=True, addplot=apds, returnfig=True)

# 标注买点区域（半透明绿色方块）
ax_main = axes[0]
ax_main.axvspan(buy_start, buy_end, alpha=0.15, color='#00e676', zorder=5)
ax_main.annotate('BUY ZONE\\n缩量回踩MA20', xy=(date, price), ...)
```

**关键参数**：`type='candle'`(K线), `volume=True`(成交量), 深色背景(#1a1a2e), 买点绿色(#00e676), 卖压区红色(#ef5350), 均线 MA5金 MA10紫 MA20绿 MA60蓝.

### 中文显示

matplotlib 默认缺少中文字体，需要手动安装：

```bash
# 无 sudo 安装 Noto Sans CJK 字体
apt-get download fonts-noto-cjk
dpkg-deb -x fonts-noto-cjk*.deb /tmp/extract
cp /tmp/extract/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc ~/.local/share/fonts/
fc-cache -f ~/.local/share/fonts/
```

然后在 Python 中激活：
```python
import matplotlib.font_manager as fm
fm.fontManager.addfont('~/.local/share/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False
```

### SELL点标注

图表现在自动标注 **SELL ① ② ③** 卖点（冲高远离MA20+放量），规则：
- 价格远离MA20 > 12%
- 量比 > 1.3
- 随后数日股价未创新高（确认滞涨）
- 最多标注最近3个代表性卖点

## ⚠️ 常见陷阱

### 1. 股票代码混淆（重要！）
| 易混淆 | 正确代码名 | 错误代码名 |
|:------|:----------|:----------|
| 生益电子 vs 生益科技 | **688183** 生益电子(科创板PCB) | ❌ 600183 生益科技(主板覆铜板) |
| A500成分股来源 | **`ak.index_stock_cons_csindex()`** 中证官网(500只) | ❌ `ak.index_stock_cons()` 新浪(仅371只) |

**规则**：科创板(688xxx/300xxx)和主板(600xxx/000xxx)同名称不同代码是两家公司，务必核实。

### 2. 数据时效性
- akshare 日线数据最新到前一个交易日
- 中证指数成分股 `index_stock_cons_csindex()` 返回最新快照
- 回测时注意复权方式 `adjust='qfq'`（前复权）

## 投星资产微博访问（用户关注）

| 信息 | 值 |
|------|-----|
| 账号 | **@投星资产** |
| UID | **1319518957** |
| 粉丝 | 117.1万 |
| 简介 | 深圳市前海朗马投星贸易发展有限公司 投资总监 |
| 微博页面 | https://weibo.com/u/1319518957 |

### 访问限制（2026.6确认）

微博2025年底起全面强制登录，所有未认证访问被拦截：
- PC版（weibo.com）：内容区显示「请登录后使用」
- 移动版（m.weibo.cn）：重定向到 Sina Visitor System
- 搜索功能：强制跳转登录页
- 短信登录：有滑块CAPTCHA，自动化浏览器无法绕过

**可尝试的方案**：
1. 🥇 **用户提供Cookie**：用 Chrome DevTools → Application → Cookies → 复制 SUB 值，注入到 WeiboSpider（GitHub: nghuyong/WeiboSpider, ⭐4.1k）
2. 🥈 **用户直接复制微博内容**：最简单，飞书发给助手分析
3. 🥉 **在其他平台搜索**：检查投星资产是否在雪球、东方财富号等有同步

## 验证与回测

A500数据库可用来验证3L选股逻辑:
```python
# 示例: 查询动量最强的板块
import sqlite3, akshare as ak
conn = sqlite3.connect("/home/zhfuyi/astock_a500.db")
# 按行业/板块分组，计算近期涨幅...

# 示例: 量价择时信号
# 放量突破 = 当日成交量 > 20日均量×1.5 + 价格突破前高
```

## 局限

- 模型偏定性，需主观判断
- 微博因登录限制未直接抓取全部发言
- 建议结合回测数据持续优化
