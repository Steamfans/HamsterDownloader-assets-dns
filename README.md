# HamsterDownloader · assets DNS sync

公开仓：同步 `assets.123123999.xyz` 的 cf-speed-dns **灰云 A** 记录（从 [ipTop](https://ip.164746.xyz/ipTop.html) 写入 Cloudflare DNS）。

## 架构

```text
cron-job.org（每 30min :10/:40 Asia/Shanghai）
    → POST workflow_dispatch API
    → GitHub Actions（本仓 sync.yml）
    → dnscf-assets.py
    → Cloudflare DNS（仅 assets 灰云 A）
```

**不使用** GitHub `on.schedule`（实测不稳定）；定时由 [cron-job.org](https://cron-job.org) 外部触发。

## Secrets（GitHub）

| Secret | 说明 |
|--------|------|
| `CLOUDFLARE_API_TOKEN` | Zone.DNS Edit（仅 `123123999.xyz`） |
| `PUSHPLUS_TOKEN` | 可选，微信通知 |

## 手动触发

```bash
gh workflow run "Sync assets DNS" -R Steamfans/HamsterDownloader-assets-dns
gh run list -R Steamfans/HamsterDownloader-assets-dns --workflow="Sync assets DNS" --limit 3
```

## cron-job.org 要点

- **URL**（repo id 短链，UI 限 100 字符）：
  `https://api.github.com/repositories/1432768135/actions/workflows/sync.yml/dispatches`
- **Method**：POST
- **Body**：`{"ref":"main","inputs":{"source":"cron-job.org"}}`
- **Authorization**：`Bearer <Fine-grained PAT>`（Actions: Read and write，仅本仓）
- **Schedule**：`10,40 * * * *`，时区 Asia/Shanghai

完整运维说明见主仓本地文档 **§4.2.14**（`doc/【小仓鼠-域名规划+解析+绑定+加速】指南.md`，主仓 `doc/` 未入库）。

## 发布

主仓修改 `scripts/dnscf-assets.py` 后：

```bash
bash scripts/publish-assets-dns-repo.sh
```
