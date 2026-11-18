# photo-mole-game · 照片变打地鼠游戏 Skill

[English](README.md) | **简体中文**

一个 Agent Skill：把**一张照片**变成**可离线运行的单文件 HTML 打地鼠游戏**。从洞里钻出来的地鼠，就是照片主人本人的卡通形象——会笑、会痛、会求饶。

整套流程已在真实项目「敲谈姐儿 v1.4.0」上完整跑通并回归验证，随后固化为可复用流水线。支持所有遵循开放标准 [Agent Skills](https://agentskills.io)（`SKILL.md`）的智能体：Claude Code、Codex、Cursor、Gemini CLI、GitHub Copilot、CodeBuddy、WorkBuddy、Trae、Qoder、Cline、Roo Code、Windsurf、Kiro 等 28 个宿主。

- **版本**：1.2.0 · **作者**：JaJa · **许可**：MIT
- **产出**：纯前端、零依赖、零联网，双击即玩（桌面与手机浏览器均可）
- **运行依赖**：Python 3.11 + `pillow numpy opencv-python`（校验阶段另需 Playwright 与本机 Edge）

---

## 它到底做什么

```
照片 ──► 卡通形象（11 张表情，纯色底）
     ──► 抠图 + 画布归一化（透明 PNG，头顶与脚底对齐）
     ──► 惊喜图（用户上传 / AI 生成 / 本地合成三选一）
     ──► config.json（主题、难度、奖励、彩蛋文案）
     ──► 构建 ──► 目录版 + 单文件版 HTML
     ──► 无头回归校验（Playwright + Edge CDP）
```

| 阶段 | 脚本 | 职责 |
| --- | --- | --- |
| 门禁 | `scripts/gate.py` | 把用户每次确认写进 `gate.json`；`--show` 随时查看缺口 |
| A | `scripts/gen_expressions.py` | 批量出 11 张表情原图（纯色底），或导出 prompt 清单交给 MCP / 线上模型 |
| A' | `scripts/make_sheet.py` | 拼小样**并同时做背景检查**（`bgcheck.json`），不合格不许发给用户 |
| B | `scripts/cutout.py` | 色度键优先，再 GrabCut、floodFill、最大连通域收尾；统一画布 |
| P | `scripts/gen_prize.py` | 惊喜图：用户上传 / AI 全身生成 / 本地 `compose` 版式合成（card、circle、badge） |
| C–D | `scripts/build_game.py` | 先校验门禁，再把 `__MOLE_CONFIG__` 注入模板，产出两种形态 |
| E | `scripts/verify_game.py` | Playwright 经 CDP 连本机 Edge，对两种形态做无头回归 |

`assets/game_template.html` 的所有可变内容都抽成了 `__MOLE_CONFIG__` 占位符——**改需求改 config，不改模板**。

### 游戏本体特性

- 默认 4 档难度（轻松 / 普通 / 困难 / 地狱），关数与命数可配；参考实现为 9 / 9 / 12 / 15 关、15 / 10 / 8 / 6 命
- 11 张表情分三组：钻出时嘲弄、被砸中时痛苦、逃跑时嘲讽
- 金蛋 / 彩蛋加命；命满时自动折算加分
- 干扰物：黑色小鸟、炸弹、核弹（高难度出现）
- 通关弹彩蛋页 + 满屏纸屑 + 「领取惊喜」图片页
- WebAudio 程序化音效，无外部素材，响应式适配手机

### 四条红线（脚本级硬门禁，不靠自觉）

`build_game.py` 会检查 `gate.json`，没确认就直接拒绝构建：

1. **照片来源必须由用户明确指定** —— 我上传 / 我给路径 / 你帮我找几张；用户选前两项时**必须停下来等**，不许自己跑去图库翻照片。
2. **表情小样必须先给用户看并确认，且背景一律纯色** —— 只允许 magenta / green / blue / white；背景检查判 `FAIL` 的图不许拿给用户当"可确认"。
3. **惊喜图的来源与覆盖范围必须先问** —— 我上传 / 系统生成 / 本地合成，再加"所有通关难度共用一张"还是"每档各一张"。
4. **除「轻松」外的每个难度都必须有惊喜图** —— `easy` 按设计没有；`normal / hard / hell` 缺一档直接构建失败。

---

## 安装

### 方式一：一键安装 EXE（GUI，推荐）

到 [Releases](https://github.com/jaja1620/photo-mole-game/releases/latest) 下载 `photo-mole-game-installer.exe`（10.0 MB，单文件，目标机免装 Python）。

| 步骤 | 会发生什么 |
| --- | --- |
| 1 | 双击 exe，弹出图形界面（Tkinter，中文） |
| 2 | **自动检测**：扫描 28 个智能体配置目录，本机装了的自动勾选，其余标「未检测」 |
| 3 | 每行显示目标目录，点该行 **浏览…** 即可改成自定义路径 |
| 4 | 点 **一键安装到勾选项**，把内置技能包（v1.2.0，18 个文件）装到 `<该智能体技能目录>/photo-mole-game` |
| 5 | 一个都没检测到、或想装到别处？用 **选择自定义目录安装…** 自选任意目录 |

几个关键行为：

- **幂等**：目标内容与内置包逐文件 sha256 一致时，输出 `[UNCHANGED]`，不写盘、不产生备份
- **覆盖前自动备份**（默认勾选）：旧版整体改名为 `photo-mole-game.bak-YYYYMMDD-HHMMSS` 后再放新版
- **结果逐条可读**：`[OK]` / `[UPDATE]` / `[UNCHANGED]` / `[SKIP]` / `[ERR]` + 路径，末尾汇总成功 / 跳过 / 失败
- **拒绝系统目录**：目标落在 `C:\Windows`、`C:\Program Files` 等位置会明确报错

同一 exe 的 CLI 模式（脚本化、静默部署）：

```bat
photo-mole-game-installer.exe --cli --list
photo-mole-game-installer.exe --cli --install --all --yes
photo-mole-game-installer.exe --cli --install --agents claude-code,cursor --dest D:\my-skills
```

运行日志写在 `%TEMP%\photo-mole-installer.log`。

### 方式二：单独安装（不用 exe）

技能本质就是「一个含 `SKILL.md` 的目录」。把本仓库的 `skill/` 整个复制到目标智能体的技能目录，**保留 `photo-mole-game/` 这一层**：

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

也可以直接用包内自带的 `skill/install.ps1`：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target "$env:USERPROFILE\.workbuddy\skills"
#   -Force   跳过"目录已存在"确认，直接覆盖（仍会先备份）
#   -DryRun  只看会做什么，不动文件
```

或者把 Releases 里的 `photo-mole-game_v1.2.0.zip` 解开后直接拖进技能目录——压缩包根就是 `photo-mole-game/`。

装完重启智能体（或在技能面板点刷新），列表里会出现 **照片打地鼠游戏生成器**。

### 各智能体的技能目录对照

| 智能体 | 目录 |
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
| 通用互操作 | `~/.agents/skills` |

一键安装器内置的正是这张表（28 条），检测逻辑为"配置目录存在即视为已安装"。

### 装完自检

```bash
pip install pillow numpy opencv-python
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --file /tmp/g.json --show
python ~/.workbuddy/skills/photo-mole-game/scripts/build_game.py --help
```

两条命令都不报错，说明包完整。`SKILL.md` frontmatter 的 `version` 与 `manifest.json` 的 `version` 应同为 `1.2.0`。

---

## 怎么用

直接对智能体说人话：

> 「用我这张照片做个打地鼠小游戏」
> 「上次那个敲一敲的，换成我妈的照片重做一版」

之后的过程：

1. 先问你**照片从哪来**（我上传 / 我给路径 / 你帮我找几张），然后停下等；
2. 出 11 张表情（纯色底）→ 拼小样 + 背景检查 → 发给你选「全部通过 / 全部重做 / 指定重做」；
3. 问**惊喜图来源**，再问「共用一张」还是「每档各一张」，以及图上文字；
4. 写 `config.json`（标题、档位、关数、命数、奖励、彩蛋文案）；
5. 构建目录版 + 单文件版，跑无头回归；
6. 交付一个双击即玩的 `.html`。

本机 GPU 参考耗时（flux.2 klein 4B / z-image-turbo，`127.0.0.1:8790` 上的 sd-server）：11 张表情约 2–4 分钟，抠图约 20 秒，构建 + 校验约 30 秒。

踩过的坑都记在 `skill/references/pitfalls.md`。

---

## 仓库结构

```
skill/                 技能包本体（v1.2.0，18 个文件）
  SKILL.md             流水线规范 + 四条红线
  scripts/             gate / 表情 / 拼图 / 抠图 / 惊喜图 / 构建 / 校验
  assets/              game_template.html（变量全部 __MOLE_CONFIG__）
  references/          配置 schema、表情清单、踩坑记录
  examples/            config.qiaotan.json、config.minimal.json
  install.ps1          PowerShell 安装脚本（备份 + 校验）
  manifest.json        逐文件 sha256
installer/             GUI 一键安装器源码
  photo_mole_installer.py    Tkinter GUI + CLI，单文件
  build.ps1 / build.bat      可复现的 PyInstaller 构建
  photo-mole-game-installer.spec
CHECKSUMS.txt          Release 附件校验值
```

## Release 附件

| 附件 | 体积 | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,464,319 字节 | `69E704925D51751801CB2831468022B48EC69DDDAEE0D0C736717A5E06D474ED` |
| `photo-mole-game_v1.2.0.zip` | 193,733 字节 | `D2B8DDF4A6165D90E95C644B327CB8B121C99A2A784285FB6D1C101AFE380D4E` |

## 版本记录

| 版本 | 变化 |
| --- | --- |
| 1.2.0 | 小样背景强制纯色 + 发图前背景检查；惊喜图按难度覆盖（轻松无、其余三档必备）；新增 `gen_prize.py --mode compose` 本地版式合成；抠图 `--chroma auto` 读 `manifest.json` |
| 1.1.0 | 门禁硬拦截：没有 `gate.json` 时 `build_game.py` 拒绝构建；小样确认回路；惊喜图来源提问 |
| 1.0.0 | 首版流水线：表情 → 抠图 → 配置 → 构建 → 无头校验 |

## 许可

MIT。作者 **JaJa**。
