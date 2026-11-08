# 狼人杀版型库

一份只读、零依赖的**狼人杀板型（版型）资料库**：把每个板子的身份构成、阵营分布和特殊规则整理成可搜索、可筛选、可复制的清单。开局前选板、给法官发配置、查「某个身份都在哪些板子里出现」都能用。

在线查看：https://wangzixiao-wzx.github.io/werewolf-boards/

> 数据规模：**69 个版型 · 120 个身份 · 184 条特殊规则 · 4 个阵营**

## 特性

- **全文搜索**：板名、身份名、特殊规则文本一起搜（按 `/` 聚焦搜索框）
- **多维筛选**：人数（6 / 9 / 10 / 12）、含第三方、含变动阵营、有特殊规则、牌数≠座位数
- **身份反查**：身份索引页点任意身份，直接列出所有使用它的板子
- **详情与复制**：按阵营分组的完整身份表 + 特殊规则全文，一键复制成可发给主持人的配置文本或 JSON
- **随机抽板**：在当前筛选结果里随机抽一个，解决「今天打什么」
- **牌数 ≠ 座位数**：盗贼 / 丘比特 / 双身份这类多牌板会单独标注，不会被当成数据错误
- 单文件前端 + 静态数据，双击 `index.html` 即可离线使用，无需服务器、无需构建

## 目录

| 文件 | 用途 |
| --- | --- |
| `index.html` | 单文件查询页（零依赖） |
| `data.js` | 前端用的数据快照（`window.BOARD_DATA`） |
| `boards.json` | 同一份数据的纯 JSON，方便别的程序复用 |
| `BOARDS.md` | 完整清单，GitHub 上可直接阅读 |
| `export_boards.py` | 从本地 `werewolf.db` 重新导出以上数据 |

## 数据说明

数据来源是自建的狼人杀对局数据库，但**导出时只读取 `board` / `board_role` / `board_rule` / `role` / `faction` 五张配置表**，从不读取 `game` / `game_player` / `player` / `player_alias` 等对局与玩家表。

因此仓库中**不含任何玩家昵称、对局记录、战绩、法官姓名或游戏时间**，可以安全公开。这一点由导出脚本的读取范围保证，而不是靠事后过滤。

字段含义：

- `seats`：座位数；`card_count`：身份牌张数；`multi_card`：两者不等（多牌机制）
- `judge`：法官人数
- `cards`：按原板子配置顺序展开的身份牌，含 `role` / `faction_id` / `count`
- `rules`：`key`（规则类别）、`value`（规则正文）、`role`（关联身份，可为空）
- `search`：预拼的检索文本，供前端快速过滤

规则文本来自自建对局复盘整理，各家村规可能不同，实际开局请以主持人口径为准。

## 本地更新

```bash
# 需要 Python 3（仅标准库），数据库默认读取 ../werewolf-stats/werewolf.db
python export_boards.py                  # 重新生成 data.js / boards.json / BOARDS.md
python export_boards.py --db 别的.db     # 指定数据库
python export_boards.py --check          # 只做一致性校验，不写文件
```

导出会校验每个板子都有身份配置、张数汇总一致、板子 id 不重复，并打印「牌数≠座位数」的板子清单。生成后刷新页面即可看到新数据。

## 部署 / 发布

仓库根目录即静态站点，GitHub Pages 选择 `main` 分支根目录；`.nojekyll` 已放置，避免 Jekyll 处理静态文件。

首次发布或后续更新可用 `publish_github.py`（仅标准库）：

```bash
python publish_github.py --token <GitHub PAT>
# 或者：GITHUB_TOKEN=<GitHub PAT> python publish_github.py
```

脚本走 **GitHub REST API**（不调用 `git push`）：验证 token → 创建或复用仓库 → 把目录内全部文件写成 blob / 目录树 → 创建提交并更新 `main` → 开启 Pages 并等待构建 → 打印在线地址。重复运行是幂等的：远端目录树与本地一致时不会新建提交。token 只通过参数或环境变量传入，不写进仓库文件、remote URL、git config 或日志输出；需要 classic PAT 的 `repo` 权限。

> 为什么不用 `git push`：部分代理 / 受限终端环境下，git 的 HTTPS 传输会挂起或反复索要用户名，而 REST API 通道正常。脚本只在本机执行 `git add` / `update-ref` 这类纯本地操作，用来让本地仓库与远端对齐。

也可以完全手动：在仓库 Settings → Pages 里选 `main / root`，文件用网页上传或普通 git 推送均可（若你的网络允许）。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
