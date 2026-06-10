---
name: hermes-autoheal
description: Hermes 永不离线 — 断电/休眠后自动恢复，配合 Windows 计划任务实现永远在线
category: devops
---

# Hermes AutoHeal — 永不离线自愈系统

断电、休眠、系统重启后自动恢复 Hermes Agent + 防休眠程序。

## 架构

```
Windows 计划任务          WSL
┌────────────────┐    ┌──────────────────────┐
│ 系统启动(+30s) │───▶│ startup_hermes.sh    │
│ 用户登录(+10s) │───▶│   ├─ keep_alive.py   │
│ 休眠恢复(+15s) │    │   │  (防休眠保活)     │
│ 失败重试×3次   │    │   └─ Hermes Gateway  │
└────────────────┘    └──────────────────────┘
```

## 已安装的文件

| 文件 | 说明 |
|:----|:------|
| `/home/zhfuyi/keep_alive.py` | 防休眠程序 — 禁用Windows休眠 + WSL保活 |
| `/home/zhfuyi/startup_hermes.sh` | 自愈启动器 — 检查/启动 keep_alive + Hermes |
| `/mnt/c/Users/周富沂/Desktop/create_task.bat` | Windows计划任务安装脚本 |

## 使用方法

### 1️⃣ 确认防休眠已运行

```bash
pgrep -af keep_alive.py
# 输出应有 python3 -u /home/zhfuyi/keep_alive.py
```

### 2️⃣ 设置 Windows 计划任务（一次性的）

**方法一：双击运行（推荐）**
1. 打开 Windows 资源管理器 → 桌面
2. 右键 `create_task.bat` → **以管理员身份运行**
3. 按提示操作

**方法二：手动创建**
1. 搜索 `任务计划程序` 打开
2. 右侧「创建基本任务」
3. 名称: `Hermes AutoHeal`
4. 触发器: `计算机启动时`
5. 操作: `启动程序`
6. 程序: `wsl.exe`
7. 参数: `-d Ubuntu -u zhfuyi bash -c 'bash /home/zhfuyi/startup_hermes.sh'`

> 建议创建 **两个触发器**：计算机启动时 + 用户登录时（双重保险）

### ⚠️ 已知坑：从 WSL 内创建 Windows 任务会失败

```bash
# ❌ 这些方法从 WSL 执行都会报 "拒绝访问" (Access Denied)
schtasks.exe /Create /SC ONSTART /TN "..." /TR "wsl.exe ..." /RU 用户名 /F
powershell.exe -ExecutionPolicy Bypass -File setup.ps1
```

**原因**：WSL 进程的 Windows 安全标识（SID）映射不完整，无权调用 Windows 任务计划程序 API。

**解决方法**：将 `.bat`/`.ps1` 文件复制到 Windows 桌面 → **右键 → 以管理员身份运行**

```bash
cp /home/zhfuyi/setup_windows_task.bat "/mnt/c/Users/用户名/Desktop/"
# 然后在 Windows 桌面右键 → 以管理员身份运行
```

### ⚠️ 环境变量变更后需重启 Gateway

在 `~/.hermes/.env` 中添加了 `LD_LIBRARY_PATH` 等环境变量后，必须重启 Hermes Gateway 才能使 `browser_navigate` 等工具生效：

```bash
hermes gateway restart
# 或在飞书: 发送 /restart
```

原因：Hermes Gateway 在启动时读取 `.env` 文件，运行时不会重新加载。

### 3️⃣ 测试自愈

```bash
# 手动模拟恢复
bash /home/zhfuyi/startup_hermes.sh

# 查看日志
tail -f /tmp/hermes_autoheal.log
```

## 防休眠程序说明 (keep_alive.py)

- 每60秒 ping DNS 保活
- 每5分钟报告一次系统状态
- 自动调用 Windows `powercfg` 关闭休眠
- 停止时自动恢复电源设置
- 占用极低 (< 0.1% CPU, < 20MB 内存)

## 文件内容

### keep_alive.py
路径: `/home/zhfuyi/keep_alive.py`

**功能:**
- 禁用 Windows 屏幕超时、休眠、磁盘休眠
- 每 60s 发送 Ping/DNS 保活
- 每 5 分钟显示系统负载
- 退出时恢复电源设置

### startup_hermes.sh
路径: `/home/zhfuyi/startup_hermes.sh`

**功能:**
1. 检查 keep_alive → 未运行则启动
2. 检查 Hermes Gateway → 未运行则启动
3. 检查网络连通性
4. 全部写入日志 `/tmp/hermes_autoheal.log`

## 参考文件

| 文件 | 说明 |
|:----|:------|
| `references/wsl-browser-deps.md` | WSL Chromium 浏览器依赖修复 (apt-get download + LD_LIBRARY_PATH，无需 sudo) |

## 故障排查

```bash
# 查看启动日志
cat /tmp/hermes_autoheal.log

# 强制启动
bash /home/zhfuyi/startup_hermes.sh

# 手动启动防休眠
python3 -u /home/zhfuyi/keep_alive.py &

# 停止防休眠
kill $(pgrep -f keep_alive.py)

# 后台运行 + 日志 (推荐)
nohup python3 -u /home/zhfuyi/keep_alive.py > /tmp/keep_alive.log 2>&1 &
```

## 开机自启 (systemd, WSL 可选)

当 WSL 支持 systemd 时可用：

```bash
sudo tee /etc/systemd/system/keep-alive.service << 'EOF'
[Unit]
Description=WSL Keep Alive
After=network.target

[Service]
ExecStart=/home/zhfuyi/.hermes/hermes-agent/venv/bin/python3 -u /home/zhfuyi/keep_alive.py
Restart=always
User=zhfuyi

[Install]
WantedBy=default.target
EOF

sudo systemctl enable keep-alive
sudo systemctl start keep-alive
```
