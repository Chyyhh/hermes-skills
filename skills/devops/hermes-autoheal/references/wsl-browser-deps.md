# WSL 浏览器依赖修复 (Chromium / Playwright)

在 WSL (Ubuntu 24.04) 上运行 Playwright Chromium 时会因缺少系统库而崩溃:
```
chrome: error while loading shared libraries: libnspr4.so: 
cannot open shared object file: No such file or directory
```

## 解决方案 (无需 sudo)

```bash
# 1. 下载 .deb 包
cd /tmp
apt-get download libnspr4
apt-get download libnss3

# 2. 解压到本地目录
mkdir -p ~/.local/lib/browser
for deb in /tmp/libnspr4*.deb /tmp/libnss3*.deb; do
    dpkg-deb -x "$deb" /tmp/extracted/
done

# 3. 复制 .so 文件
cp /tmp/extracted/usr/lib/x86_64-linux-gnu/lib{nspr4,nss3,nssutil3,smime3,ssl3,plc4,plds4,softokn3,nssckbi,freebl3,nssdbm3,freeblpriv3}.so \
   ~/.local/lib/browser/

# 4. 设置 LD_LIBRARY_PATH (永久生效)
echo 'export LD_LIBRARY_PATH=/home/zhfuyi/.local/lib/browser' >> ~/.bashrc
source ~/.bashrc

# 5. 验证
LD_LIBRARY_PATH=$HOME/.local/lib/browser \
    $HOME/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome --version
# 应输出: Google Chrome for Testing 148.0.7778.96
```

## 为什么需要这个

- Hermes 的 `browser_navigate` / `browser_click` 工具依赖 Chromium
- WSL 默认没有安装 libnspr4/libnss3 这些基础库
- `sudo apt-get install` 需要密码且普通用户无 sudo 权限
- 上述方法完全不用 sudo

## 注意事项

- if `/home/zhfuyi/.cache/ms-playwright/` 下有多个版本，选最新的
- `browser` 工具运行时需要 LD_LIBRARY_PATH 已生效
- 如果重启 Hermes Gateway 后浏览器仍报错，把变量加到 `.env`:
  ```
  echo 'LD_LIBRARY_PATH=/home/zhfuyi/.local/lib/browser' >> ~/.hermes/.env
  ```
