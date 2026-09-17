# iPhone 18 Pro Max 512GB 冰川蓝色 — 北京门店库存监控

监控北京 6 家 Apple Store 的 iPhone 18 Pro Max 512GB 冰川蓝色（`MJYE4CH/A`，¥12,999）**到店取货**库存，有货时通过微信推送通知。

- 📊 **监控面板**：https://jz-xiong.github.io/iphone-stock-probe/
- ⏱ **检查频率**：每 10 分钟（GitHub Actions）
- 🔔 **通知**：仅在有变化时推送，无变化完全静默

## 数据来源

```
GET https://www.apple.com.cn/shop/retail/pickup-message
    ?parts.0=MJYE4CH/A&searchNearby=true&store=R320
```

字段 `body.stores[].partsAvailability["MJYE4CH/A"].pickupDisplay`：

| 值 | 含义 |
|---|---|
| `available` | 可门店取货 |
| `unavailable` | 目前无货 |
| `ineligible` | 暂未开放取货（新品发售前常见） |

## 监控的门店

| 门店号 | 门店 |
|---|---|
| R320 | 三里屯 |
| R448 | 王府井 |
| R479 | 华贸购物中心 |
| R388 | 西单大悦城 |
| R645 | 朝阳大悦城 |
| R792 | 北京荟聚 |

## 开启微信推送

在仓库 **Settings → Secrets and variables → Actions** 添加任意一个（可同时配多个，都会收到）：

### 方案 A：WxPusher（推荐，永久免费）

1. 打开 https://wxpusher.zjiecode.com/docs/spt.html ，用微信扫码获取 `SPT_` 开头的令牌
2. 添加 Secret：名 `WXPUSHER_SPT`，值填你的 SPT

### 方案 B：PushPlus

1. 打开 https://www.pushplus.plus/ 微信扫码登录，复制 token
2. 添加 Secret：名 `PUSHPLUS_TOKEN`

### 方案 C：Server酱

1. 打开 https://sct.ftqq.com/sendkey 微信扫码获取 SendKey（免费版每天 5 条）
2. 添加 Secret：名 `SERVERCHAN_KEY`

**没配任何 Secret 也能用**，只是不推送微信，监控面板照常更新。

## 本地运行

```bash
python check_stock.py
```

产出 `docs/data/status.json`（面板数据）与 `docs/data/state.json`（比对基线）。

## 架构说明

Apple 接口的 `Access-Control-Allow-Origin` 只回 `https://www.apple.com`，浏览器跨域被拦，
所以纯前端页面无法直连。这里用 GitHub Actions 作为免费后端：

```
GitHub Actions (每10分钟)
   └─ check_stock.py 抓 Apple 接口
        ├─ 写 docs/data/*.json → commit 回仓库 → GitHub Pages 渲染面板
        └─ 检测到变化 → 调推送 API → 微信通知
```

已验证 GitHub Actions 的美国服务器返回结果与国内直连**完全一致**，Apple 未对此接口做地理围栏。
