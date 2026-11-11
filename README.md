# ✈️ 吉隆坡出发 Bug 价雷达

每 15 分钟自动扫描「吉隆坡 → 全世界」的机票价格，发现疑似 bug 价（错误票价）或低于目标价时，**立刻推送到手机**，同时更新一个网页看板。

全部跑在 GitHub 上：**免费、不用服务器、电脑关机也照常运行**。

```
GitHub Actions（每15分钟）
   ├─ Aviasales 实时低价缓存（KUL 出发所有目的地，经济舱+商务舱，往返+单程）
   ├─ 错误票价情报 RSS（Secret Flying / Google 新闻 / Fly4free）
   ├─ 异常判定：对比该航线近60天常规价 / 每公里单价 / 你设的目标价
   ├─ 推送：Telegram / ntfy / Bark / 微信(Server酱、PushPlus) / 邮件
   └─ 更新网站数据 → GitHub Pages 网页
```

---

## 一、10 分钟部署

### 1. 建仓库并上传代码
1. 打开 GitHub → 右上角 **+ → New repository**，名字例如 `flight-ticket`，选 **Public**（公开仓库 Actions 分钟数无限免费；私有仓库每 15 分钟跑一次会超出免费额度）。
2. 把这个文件夹里的所有文件上传（网页上 **Add file → Upload files** 拖进去，或用 git push）。注意 `.github` 文件夹也要传上去。

### 2. 申请免费的票价数据 token（核心数据源）
1. 注册 <https://www.travelpayouts.com>（可用 Google 账号登录）。
2. 在 Programs 里搜索 **Aviasales** 并加入（Join）。
3. 右上角头像 → **Profile → API token**，复制那串 token。
4. 回到 GitHub 仓库 → **Settings → Secrets and variables → Actions → New repository secret**  
   名字 `TRAVELPAYOUTS_TOKEN`，值粘贴 token。

> 不配 token 也能跑，但只剩 RSS 情报，抓不到实时价格。

### 3. 选一个推送渠道（可以同时配多个）

| 渠道 | 适合 | 需要的 Secret | 获取方式 |
|---|---|---|---|
| **Telegram**（推荐） | 最快最稳，免费无限量 | `TELEGRAM_BOT_TOKEN` `TELEGRAM_CHAT_ID` | 找 @BotFather 发 `/newbot` 拿 token；给你的 bot 发一句话，再打开 `https://api.telegram.org/bot<token>/getUpdates` 找 `chat.id` |
| **ntfy**（最省事） | 不用注册，装 App 就行 | `NTFY_TOPIC` | 手机装 ntfy App → 订阅一个**别人猜不到**的主题名，如 `ritchie-kulfare-8x2k`，把同名填进 Secret |
| **Bark** | iPhone 原生通知 | `BARK_KEY` | App Store 装 Bark，复制 URL 里 `api.day.app/` 后面那段 key |
| **Server酱** | 推到微信 | `SERVERCHAN_KEY` | <https://sct.ftqq.com> 微信扫码登录拿 SendKey（免费版每天 5 条） |
| **PushPlus** | 推到微信 | `PUSHPLUS_TOKEN` | <https://www.pushplus.plus> 微信登录拿 token |
| **邮件** | 备份渠道 | `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASS` `MAIL_TO` | Gmail：`smtp.gmail.com` / `465` / 你的邮箱 / [应用专用密码](https://myaccount.google.com/apppasswords) |

### 4. 打开网页
仓库 **Settings → Pages** → Source 选 **Deploy from a branch** → Branch 选 `main`，文件夹选 **`/docs`** → Save。  
一两分钟后网址会显示在页面顶部，形如 `https://你的用户名.github.io/flight-ticket/`。

### 5. 启动并测试推送
1. 仓库 **Actions** 标签 → 如果提示启用 workflow，点启用。
2. 左边选「Bug 价机票监控」→ **Run workflow** → 勾选「只发一条测试推送」→ Run。手机收到测试消息就说明推送通了。
3. 再 Run 一次（不勾选），跑一轮真实监控。之后每 15 分钟自动运行。
4. 把网页地址填进 `config.yaml` 的 `notify.site_url`，推送里就会带上看板链接。

---

## 二、调整监控规则（编辑 `config.yaml`）

- **目标价** `detection.targets`：最常用。比如想要 RM1500 以内的伦敦往返，就写 `LON: 1500`。城市代码用 IATA 城市码（TYO 东京、OSA 大阪、SEL 首尔、LON 伦敦、PAR 巴黎、SYD 悉尼、YVR 温哥华、CTU 成都…）。
- **bug 价灵敏度**：
  - `bug_ratio: 0.45` → 低于该航线近期常规价 45% 判为 bug。想要更多提醒就调高（如 0.5），嫌吵就调低。
  - `economy_bug_per_km` / `business_bug_per_km` → 按距离算的单价门槛，新航线没历史数据时靠它判断。
- **推送哪些级别** `notify.push_levels`：默认 `[bug, target]`；加上 `great` 会收到更多「超值」提醒；加 `news` 会推送所有吉隆坡特价情报。
- **多出发地** `extra_origins: [PEN, SIN]`：同时监控槟城、新加坡出发。
- **新加坡出发的错误票价也要** `rss.push_global_errors: true`。

改完直接在 GitHub 网页上编辑提交即可，下一轮生效。

---

## 三、它是怎么判断 bug 价的

1. **对比历史**：每条航线（目的地 × 往返/单程 × 舱位）每天记一个最低价，保留 60 天。现价 ≤ 历史中位数 × 45% → 🔥 疑似 bug；≤ 65% → 💎 超值。前 5 天在积累数据，这条规则还不生效。
2. **每公里单价**：经济舱往返每公里 ≤ RM0.045（吉隆坡-伦敦往返约 RM950）、商务舱 ≤ RM0.14 → 🔥。短于 1800 km 的航线不用这条，避免亚航促销刷屏。
3. **目标价**：低于你在 `targets` 里写的价格 → 🎯。
4. **情报**：RSS 里同时出现「吉隆坡」和「error fare / 错误票价」等词 → 🔥 推送。

同一航线 24 小时内不重复推送，除非价格又降了 10% 以上。

---

## 四、注意事项

- Aviasales 数据是用户近 2–7 天搜索的**缓存价**，可能已经失效。收到推送后点「Google 核价」或去航司官网确认，看到真有就尽快下单。
- 第一周以「目标价」和「每公里」规则为主；历史数据积累到一两周后，「对比历史」会越来越准。
- Secret Flying 有反爬，GitHub 服务器有时抓不到，网页底部「数据源」会显示红点，属正常，其他源不受影响。
- GitHub 定时任务在高峰期可能延迟 5–15 分钟。
- 本地试跑：`pip install -r requirements.txt && python -m monitor.main --demo`，然后 `cd docs && python -m http.server` 打开 <http://localhost:8000> 看演示页面。
