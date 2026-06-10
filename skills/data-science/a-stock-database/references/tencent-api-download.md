# Tencent Finance API — A股历史日线下载

## 端点

```
GET http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{n},qfq
```

## 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| prefix | sh(沪) / sz(深) | sh600519 |
| code | 6位股票代码 | 600519 |
| n | 返回最近n根K线 | 1（只需当日）/ 60（扫描用） |
| qfq | 前复权 | 固定值 |

## 返回格式

```json
{
  "code": 0,
  "data": {
    "sh600519": {
      "qfqday": [
        ["2026-06-09", "1684.00", "1698.00", "1702.00", "1678.00", "45423.000"]
      ]
    }
  }
}
```

**qfqday 每条**：`[date, open, close, high, low, volume(手)]`
- volume 需 **×100** 转换为股
- 无 amount（成交额），可填0

## 性能

- 协议：HTTP/2
- 速度：~0.3s/请求（含0.05s间隔）
- 批量：82秒下载250只（含50只批量commit）
- 稳定性：WSL环境实测97%+成功率
- 无需API Key，无IP限制

## 完整脚本

见项目根目录 `scripts/download_a500.py`（支持断点续传、失败重试、`--all` 全量模式）
