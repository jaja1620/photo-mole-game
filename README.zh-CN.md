# photo-mole-game · 照片打地鼠游戏生成器

[English](README.md) | **简体中文**

一个 Agent Skill：把**一张照片**变成**离线、单文件、双击即玩**的打地鼠小游戏——地洞里冒头的，就是照片里的人，只是变成了会嘲笑、会疼、会求饶的卡通小人。

在真实项目（`敲谈姐儿 v1.4.0`）里端到端跑通并做过回归验证，之后固化成可复用流水线。适用于任何支持开放 [Agent Skills](https://agentskills.io) `SKILL.md` 格式的 Agent：Claude Code、Codex、Cursor、Gemini CLI、GitHub Copilot、CodeBuddy、WorkBuddy、Trae、Qoder、Cline、Roo Code、Windsurf、Kiro 等 30 余款。

- **版本**：1.3.0 · **作者**：JaJa · **许可**：MIT
- **产出**：纯前端、零依赖、零联网，双击即玩（桌面浏览器 / 手机浏览器均可）
- **运行依赖**：Python 3.11 + `pillow numpy opencv-python`（验证环节另需 Playwright + 本机 Edge）
- **出图**：不绑定模型，任何本地 `sd-server` / MCP 托管引擎或线上模型都能接入，见 [与本地图形模型配合](#与本地图形模型配合)

---

## 它做什么

```
照片 ──► 真人特征分析（22 键特征，提示词身份锁定）
     ──► 卡通形象（11 张表情，纯色背景）
     ──► 与原照片的身份相似度评分（≥ 80 才交付）
     ──► 抠图 + 画布统一（分析 → 定参 → 抠图 → 比对）
     ──► 惊喜图（用户上传 / AI 生成 / 本地合成）
     ──► config.json（主题、难度、奖励、彩蛋）
     ──► 构建 ──► 文件夹版 + 单文件 HTML
     ──► 无头回归验证（Playwright + Edge CDP）
```

| 阶段 | 脚本 | 职责 |
| --- | --- | --- |
| 门禁 | `scripts/gate.py` | 把用户确认项写进 `gate.json`（照片 / 小样 / 惊喜图 / 身份）；`--show` 列出还缺什么 |
| A0 | `scripts/identity.py` | 22 键面部特征模板 → 英文 `desc`、身份锁定正向词与负向词、原图 vs 卡通相似度评分 |
| A | `scripts/gen_expressions.py` | 在纯色背景上批量生成 11 张表情原图；或只导出提示词清单交给 MCP / 线上模型 |
| A' | `scripts/make_sheet.py` | 拼小样**并跑背景检查**（`bgcheck.json`），先过检再给用户看 |
| B | `scripts/cutout.py` | `--analyze` 分析色距 → 定参 → 色度键 + GrabCut + 连通域（含主体保护）→ `--verify` 出报告 → `--compare` 出对照图 |
| P | `scripts/gen_prize.py` | 惊喜图：用户上传 / AI 全身生成 / 本地 `compose` 版式（卡片 / 圆图 / 徽章） |
| C–D | `scripts/build_game.py` | 校验门禁与抠图报告，把 `__MOLE_CONFIG__` 注入模板，输出两种构建形态 |
| E | `scripts/verify_game.py` | 用 Playwright + Chrome DevTools Protocol 驱动本机 Edge，对两种构建做无头回归 |

`assets/game_template.html` 里所有变量都是 `__MOLE_CONFIG__` 占位符——**只改配置，不改模板**。

### 游戏内容

- 4 个难度档（轻松 / 普通 / 困难 / 地狱），关卡数与生命数可配——参考实现为 9 / 9 / 12 / 15 关，15 / 10 / 8 / 6 条命
- 11 张表情：冒头嘲讽、挨打受伤、逃跑各有不同脸
- 金蛋 / 彩蛋加命，命上限时自动折算成分数
- 障碍物：黑鸟、炸弹、核弹（高难度档出现）
- 每通过一档弹出彩蛋页，撒彩纸 + "领取奖品"图
- WebAudio 程序化音效，无外部素材，全响应式

### 六条硬红线（由脚本强制，不靠自觉）

`gate.json` 里任一环节没通过，`build_game.py` 直接拒绝构建：

1. **照片来源必须由用户指定**——上传 / 本地路径 / "从我的图库挑几张"，必须停下来等回答，禁止自行去翻相册。
2. **表情小样必须先给用户看并确认，且背景必须纯色**——只允许 `magenta / green / blue / white` 四种色度背景；背景检查判 `FAIL` 的小样不得当成"可通过"交给用户。
3. **惊喜图来源与覆盖范围必须先问**——上传 / 自动生成 / 本地合成三选一，并明确"所有难度共用一张"还是"每档一张"。
4. **除轻松档外，每档都必须有自己的惊喜图**——`easy` 按设计不配；`normal / hard / hell` 各需一张定稿，否则拒建。
5. **抠图禁止吞掉主体、衣服、配件**——抠前必须分析参数，抠后必须比对；白衬衫变透明、眼镜没了、头边紫边、耳饰消失都算明确失败。
6. **卡通必须基于真人特征分析且相似度达标**——没有 `features.json` 不许出图，评分 < 80 改特征重出，< 65 拒建。

---

## 与本地图形模型配合

技能本身**不带模型、也不直连任何厂商 API**：出图是一句 HTTP 调用，所以任何本地引擎（stable-diffusion.cpp / `sd-server`，A1111 兼容接口）或线上模型都能驱动它。

### 三种接法

| 路径 | 做法 | 适用 |
| --- | --- | --- |
| **A. 本地批量（推荐）** | 起 `sd-server`，脚本直接给 `--endpoint http://127.0.0.1:8790`，11 张表情一条命令出完 | 引擎已常驻 |
| **B. 走 MCP** | `gen_expressions.py --manifest-only` 导出 `raw/manifest.json`，Agent 逐张调 `locmodel-image` 的 `redraw_image(init_image=照片, prompt=…, negative_prompt=…, strength=0.66, seed=…)` | 引擎由 MCP 托管，或想让它自动选模型 |
| **C. 线上模型** | 同一份清单交给线上图生图模型，按 `raw/<key>.png` 回传 | 本机无 GPU |

### 引擎检查（MCP 路线）

`locmodel_status`（端口 / 已载模型 / 显存）→ `engine_discover`（重启后端口可能变）→ `engine_doctor`（出图失败先自查）→ `list_models` / `list_edit_models` / `load_model`（切换并等引擎确认载入）。实测可用：**flux2-klein（flux.2 klein 4B）**、**z_image_turbo（z_image_turbo-Q4_K）**，均支持 img2img；1024×1024 单张约 20–60 秒（中端显卡）。

### 必须对齐的参数

| 参数 | 表情 | 惊喜图 | 说明 |
| --- | --- | --- | --- |
| `--strength` | `0.66`（0.55–0.75） | `0.80`（0.78–0.88） | 太低不变、太高脱离本人 |
| `--steps` / `--sampler` / `--cfg` | `20` / `euler` / `7.0` | `24` / `euler` / `7.0` | 蒸馏模型按模型卡下调 |
| `--width` × `--height` | `832 × 1024` | `832 × 1216` | 8 的倍数 |
| `--seed` | `20261112`（每张 + idx×13） | `20261118` | 固定种子可复现 |
| `--bg` | `magenta` / `green` / `blue` / `white` | 不涉及 | 只许纯色，色值写入 `manifest.json` → `bg.hex` |

### 决定能否过闸的几条规矩

- **init_image 必须是被拍者本人**：表情阶段用用户照片，惊喜图阶段用 `assets/normal.png`。
- **必须带 `--features features.json`**：它会重写 `desc`、追加 11 条身份锁定正向词与 9 条负向词。不带就是"通用动漫脸"，身份评分几乎必然跌破 65，构建被拒。
- **不许手改导出的 prompt**：纯背景条款与负向词同时被抠图和身份评分依赖，删了就两头翻车。
- **模型只负责"画"**：抠图、身份评分、门禁、构建、回归全在本地 CPU 完成，不联网；技能也不改引擎自身配置，参数按任务走 HTTP 载荷。

完整细节（含出图后的三道闸与自检命令）见 [RELEASE_NOTES_v1.3.0.md](RELEASE_NOTES_v1.3.0.md)。

---

## 安装

### 方式 A —— 一键安装器（GUI，推荐）

从 [Releases](https://github.com/jaja1620/photo-mole-game/releases/latest) 下载 `photo-mole-game-installer.exe`（10.4 MB，单文件，目标机免装 Python）。

| 步骤 | 说明 |
| --- | --- |
| 1 | 双击 exe，弹出图形界面（Tkinter，中文） |
| 2 | **自动检测**：扫描 31 个 Agent 配置目录，已检测到的默认勾选，其余显示"未检测" |
| 3 | 每行都显示目标目录，点行内 **浏览…** 可单独改路径 |
| 4 | 点 **一键安装到勾选项**，把内置技能包（v1.3.0，19 文件 / 408,571 字节）装到 `<agent-skills 目录>/photo-mole-game` |
| 5 | 一个都没检测到，或想装到私有目录？用 **选择自定义目录安装…** 任选一个目录 |

需要知道的行为细节：

- **幂等**——目标目录与载荷逐字节一致时显示 `[UNCHANGED]`，不写盘
- **覆盖前自动备份**（默认开启）——旧安装改名为 `photo-mole-game.bak-YYYYMMDD-HHMMSS`
- **结果日志**——逐行 `[OK]` / `[UPDATE]` / `[UNCHANGED]` / `[SKIP]` / `[ERR]` 加路径，末尾给汇总
- **拒绝系统目录**——装进 `C:\Windows`、`C:\Program Files` 等会明确报错
- **豆包工作**走手动导入：导出到 `~/photo-mole-game-import`（技能目录 + 技能 zip + 导入指引），因为该应用自管技能工作区

CLI 模式（同一个 exe，适合脚本或静默部署）：

```bat
photo-mole-game-installer.exe --cli --list
photo-mole-game-installer.exe --cli --install --all --yes
photo-mole-game-installer.exe --cli --install --agents claude-code,cursor --dest D:\my-skills
```

日志固定写 `%TEMP%\photo-mole-installer.log`。

### 方式 B —— 手动安装（不用 exe）

技能就是一个含 `SKILL.md` 的目录。把本仓库 `skill/` 复制进 Agent 的技能目录，保留 `photo-mole-game/` 这一层：

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.workbuddy\skills" | Out-Null
Copy-Item .\skill "$env:USERPROFILE\.workbuddy\skills\photo-mole-game" -Recurse
```

```bash
# macOS / Linux
mkdir -p ~/.workbuddy/skills
cp -r skill ~/.workbuddy/skills/photo-mole-game
```

技能包内也带了 `skill/install.ps1`：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target "$env:USERPROFILE\.workbuddy\skills"
#   -Force   不再询问，直接覆盖（仍会先备份）
#   -DryRun  只显示将要发生什么，不动磁盘
```

也可以直接把 Releases 里的 `photo-mole-game_v1.3.0.zip` 解压到技能目录——压缩包根目录已经是 `photo-mole-game/`。

重启（或刷新技能面板）后，技能以 **照片打地鼠游戏生成器 / Photo Whack-a-Mole Game** 出现。

### 各 Agent 的技能目录（用户级）

| Agent | 目录 |
| --- | --- |
| Claude Code | `~/.claude/skills` |
| Codex | `~/.codex/skills` |
| Cursor | `~/.cursor/skills` |
| Gemini CLI | `~/.gemini/skills` |
| Antigravity | `~/.gemini/antigravity/skills` |
| GitHub Copilot | `~/.copilot/skills` |
| CodeBuddy | `~/.codebuddy/skills` |
| WorkBuddy | `~/.workbuddy/skills` |
| Trae | `~/.trae/skills` |
| Qoder | `~/.qoder/skills` |
| Cline | `~/.cline/skills` |
| Roo Code | `~/.roo/skills` |
| Windsurf | `~/.codeium/windsurf/skills` |
| Kiro CLI | `~/.kiro/skills` |
| Kilo Code | `~/.kilocode/skills` |
| OpenCode | `~/.config/opencode/skills` |
| OpenHands | `~/.openhands/skills` |
| Goose | `~/.config/goose/skills` |
| Amp | `~/.config/agents/skills` |
| Qwen Code | `~/.qwen/skills` |
| Command Code | `~/.commandcode/skills` |
| Droid | `~/.factory/skills` |
| Clawdbot | `~/.clawdbot/skills` |
| MCPJam | `~/.mcpjam/skills` |
| Neovate | `~/.neovate/skills` |
| Pi | `~/.pi/agent/skills` |
| Zencoder | `~/.zencoder/skills` |
| DeepSeek Harness | `~/.dsh/skills` |
| Kimi | `~/.kimi/skills` |
| 豆包工作（手动导入） | `~/photo-mole-game-import` |
| 任意 Agent（通用） | `~/.agents/skills` |

一键安装器内置的就是这张表（31 项），按"配置目录是否存在"判断是否检测到。

### 验证安装

```bash
pip install pillow numpy opencv-python
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --file /tmp/g.json --show
python ~/.workbuddy/skills/photo-mole-game/scripts/build_game.py --help
```

两条命令都能跑通就说明包是完整的。`SKILL.md` frontmatter 的 `version` 与 `manifest.json` 的 `version` 都应为 `1.3.0`。

---

## 怎么用

直接用自然语言跟 Agent 说：

> "用我这张照片做个打地鼠小游戏"

Agent 会依次：

1. 问**照片从哪来**（上传 / 路径 / 从图库挑）并等待回答；
2. 分析人物面部特征，产出 `features.json`（阶段 A0）；
3. 在纯色背景上生成 11 张表情，把卡通与原照片比对评分，拼小样问 **全部通过 / 全部重出 / 重出这几张**；
4. 问**惊喜图从哪来**、是否所有难度共用一张；
5. 抠图并做分析与比对，报告里出现任何 FAIL 就停下返工；
6. 写 `config.json`（标题、难度、关卡、生命、奖励、彩蛋文案）；
7. 构建文件夹版与单文件 HTML，跑无头回归；
8. 交给你一个双击即玩的 `.html`。

遇到问题，`skill/references/pitfalls.md` 收着踩过的坑。

---

## 仓库结构

```
skill/                 技能包本体（v1.3.0，19 文件）
  SKILL.md             流水线规范 + 六条红线
  scripts/             gate / identity / expressions / sheet / cutout / prize / build / verify
  assets/              game_template.html（变量全是 __MOLE_CONFIG__）
  references/          配置 schema、表情清单、踩坑记录
  examples/            config.qiaotan.json、config.minimal.json
  install.ps1          PowerShell 安装脚本（备份 + 校验）
  manifest.json        逐文件 sha256
installer/             一键安装器源码（v1.3.0，31 个 Agent）
  photo_mole_installer.py    Tkinter GUI + CLI，单文件
  build.ps1 / build.bat      可复现的 PyInstaller 构建（载荷 = payload/photo-mole-game）
  photo-mole-game-installer.spec   可移植 spec，载荷定位方式一致
CHECKSUMS.txt          v1.3.0 交付物 sha256
RELEASE_NOTES_v1.3.0.md / .en.md   中英文发布说明
```

## 发布资产

| 资产 | 大小 | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,436,783 B | `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| `photo-mole-game_v1.3.0.zip` | 155,111 B | `4A63F892FB07F2D7239DF1274D7BF7465D779F80E169655060249F973858035E` |
| `CHECKSUMS-v1.3.0.txt` | 2,839 B | — |
| `RELEASE_NOTES_v1.3.0.md`（中文）/ `.en.md`（English） | — | — |

## 版本记录

| 版本 | 要点 |
| --- | --- |
| 1.3.0 | 抠图加固（`--analyze` 参数建议、默认开启主体保护、`--verify` 九项指标报告、`--compare` 对照图）+ 身份加固（新增 `identity.py` 22 键特征模板、`--features` 身份锁定、`gate.py` / `build_game.py` 身份门禁）。红线 4 → 6。安装器覆盖 31 个 Agent |
| 1.2.0 | 纯色背景规范 + 小样背景检查；惊喜图按难度分别覆盖；`gen_prize.py --mode compose` 本地版式合成；`--chroma auto` 读 `manifest.json` 抠图 |
| 1.1.0 | 门禁硬失败：无 `gate.json` 拒建；小样确认闭环；惊喜图来源提问 |
| 1.0.0 | 首版流水线：表情 → 抠图 → 配置 → 构建 → 无头验证 |

## 许可

MIT。作者 **JaJa**。
