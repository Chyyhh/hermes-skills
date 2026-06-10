# 微博访问限制 — 2026.6 实测

## 全面封锁确认

微博2025年底起对所有未登录访问实施全面封锁。以下路径均已实测确认：

| 路径 | URL | 结果 |
|------|-----|------|
| PC主页 | weibo.com/u/{uid} | 页面加载但内容区「请登录」 |
| 移动版 | m.weibo.cn/u/{uid} | 重定向到 Sina Visitor System（空页） |
| 搜索微博 | s.weibo.com/weibo?q=... | 强制跳转登录页 |
| 搜索用户 | s.weibo.com/user?q=... | ⚠️ 可用！能找到账号但看不到微博 |
| 短信API | passport.weibo.cn/sso/v2/... | 404，接口已关闭 |
| 桌面版登录 | passport.weibo.com/sso/signin | 有滑块CAPTCHA，Playwright无法绕过 |

## 唯一可行的自动化方案

### WeiboSpider（GitHub: nghuyong/WeiboSpider，⭐4.1k）

```bash
git clone https://github.com/nghuyong/WeiboSpider.git --depth 1
cd WeiboSpider && pip install -r requirements.txt
```

**关键步骤**：用户需提供登录后的 Cookie：
1. 用电脑浏览器登录 weibo.com
2. F12 → Application → Cookies → weibo.com → 复制 `SUB` 值
3. 写入 `weibospider/cookie.txt`

## 投星资产账号信息

- 账号：@投星资产
- UID：1319518957
- 粉丝：117.1万
- 认证：热门财经博主，VIP4
- 简介：深圳市前海朗马投星贸易发展有限公司 投资总监

注意：存在大量冒名账号（投星l资产、投星---资产、投星资产短线等），UID 1319518957 是真实主号。
