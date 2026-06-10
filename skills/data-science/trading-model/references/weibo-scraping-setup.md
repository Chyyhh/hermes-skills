# 微博「投星资产」观点抓取方案

## 目标
抓取 **投星资产**（UID 1319518957, 117万粉丝, 财经博主）的最新微博观点和推荐股票，补充交易模型的外部信息。

## 障碍
微博 2025 年后全面锁死未登录访问：
- PC版主页：内容区显示「请登录后使用」
- 移动版 m.weibo.cn：重定向到 Sina Visitor System（游客拦截）
- 搜索功能：强制跳转登录页
- 短信API：已关闭
- RSSHub / 第三方镜像：均失效

## 解决方案：WeiboSpider

**仓库**：https://github.com/nghuyong/WeiboSpider (⭐4.1k)
**安装位置**：`/home/zhfuyi/WeiboSpider/`
**原理**：基于 weibo.com 新版 API，通过 Cookie 认证抓取

### 安装步骤（已完成）
```bash
git clone https://github.com/nghuyong/WeiboSpider.git --depth 1
cd WeiboSpider
pip install -r requirements.txt  # scrapy, twisted, etc.
```

### 获取 Cookie（待用户提供）
1. 用户用电脑浏览器登录 https://weibo.com （账号 18859161052）
2. F12 → Application → Cookies → weibo.com
3. 复制 `SUB` Cookie 的值（格式：`_2A25Mxxxx...`）
4. 写入 `weibospider/cookie.txt`

### 采集命令
```bash
# 用户微博帖子
cd /home/zhfuyi/WeiboSpider/weibospider
# 修改 spiders/user_tweet.py 的 start_requests 中 user_id 为 '1319518957'
python run_spider.py tweet
```

### 待办
- [ ] 用户提供 SUB Cookie
- [ ] 配置 spider 采集投星资产微博
- [ ] 建立定时任务：每日自动抓取最新观点，提取股票代码
- [ ] 将观点整合到选股扫描报告中
