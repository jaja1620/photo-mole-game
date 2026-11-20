---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_26942b9ce31811f1b140525400de85a5
    ReservedCode1: aOhYXcyjVe/3NuNTTnU/bjzTuSxjSKuAmnGtwjABoGpXeqJ30JPPL2JNTk7TD9yxDueqhax8CpU7J9fM5Abkkz9jkmWb6LMzpU/Z+0nEJNtGMKRRODq2XXw0duugnPqAmjuQc7MAgOo6EGWVnmYUIk4qNBoOhOFnuRJyW/jGzO9YsZQ049OPTnOfKGg=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_26942b9ce31811f1b140525400de85a5
    ReservedCode2: aOhYXcyjVe/3NuNTTnU/bjzTuSxjSKuAmnGtwjABoGpXeqJ30JPPL2JNTk7TD9yxDueqhax8CpU7J9fM5Abkkz9jkmWb6LMzpU/Z+0nEJNtGMKRRODq2XXw0duugnPqAmjuQc7MAgOo6EGWVnmYUIk4qNBoOhOFnuRJyW/jGzO9YsZQ049OPTnOfKGg=
---

# photo-mole-game 技能一键安装器（v1.3.0）

面向主流 AI Agent / CLI 编程工具的**技能一键安装器**：单个 exe，双击即用。自动检测本机已安装的 Agent，按其技能目录规则把 `photo-mole-game` v1.3.0 技能装进去；也支持手动勾选 Agent 与自定义目标目录。

- 技能版本：**v1.3.0**
- 内置载荷：**19 个文件 / 408,571 字节**（构建时嵌入 exe，运行时解包到临时目录，无外部依赖）
- 运行环境：Windows 7 SP1 及以上 / Windows 10、11（x64），无需安装 Python
- 界面：Tkinter（Python 标准库），单文件 windowed exe（PyInstaller `--onefile --windowed`）

---

## 1. 目录结构与交付清单

| 文件 | 体积（字节） | SHA256 |
| --- | --- | --- |
| `dist\photo-mole-game-installer.exe` | 10,436,783 | `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| `photo_mole_installer.py` | 44,607 | `80EF3771EEF8BAFA43E42C6308AC7267EEDB0A370F9D3CCCAD3080CBC6F776A2` |
| `build.ps1` | 3,043 | `0C16DE48EB4D77D94EFF5030F72C5D88F0452010D7A1D4620973D471E9095331` |
| `build.bat` | 359 | `4BEF8401CF09DD5EF6901CE1B905F808BE814693D48E72FE91F3B195E2A4ACD6` |
| `photo-mole-game-installer.spec` | 950 | `29834BC50799F6279FA9C79A51FEE202EB6C3740CEED74B7EE625D256C7610BC` |
| `dist\gui_screenshot.png` | 81,346 | `24E53D5D0515E1F274FD38DB6428373917E0F491D0845DB67966E1B1D404424B` |
| `README.md` | 见 `CHECKSUMS.txt`（本文件自身哈希与体积以校验清单为准） | 见 `CHECKSUMS.txt` |

> 完整校验清单见 `CHECKSUMS.txt`（7 个文件，`Get-FileHash` 逐项核对）。

```
photo-mole-installer\
├─ dist\
│  ├─ photo-mole-game-installer.exe   ← 分发这个文件即可
│  └─ gui_screenshot.png              ← 界面截图（验收留档）
├─ photo_mole_installer.py            ← 源码（GUI + CLI + 安装逻辑）
├─ build.ps1 / build.bat              ← 一键构建脚本
├─ photo-mole-game-installer.spec     ← PyInstaller 规格（自动生成）
├─ README.md
└─ CHECKSUMS.txt
```

---

## 2. GUI 使用

双击 `photo-mole-game-installer.exe`，无需命令行参数。

1. **看检测结果**：列表列出全部 31 个 Agent，`检测` 列显示「已检测 / 未检测」，`已装版本` 列显示目标目录里已有的版本（本机当前 WorkBuddy 已装 v1.3.0）。
2. **调勾选**：已检测到的 Agent **默认勾选**；用「全选已检测」「全不选」批量调整，或逐行勾选未检测项。目标目录可逐行点「浏览…」改成自定义路径。
3. **设覆盖策略**：勾选「覆盖已存在的安装（覆盖前自动备份为 `photo-mole-game.bak-时间戳`）」，默认开启。
4. **执行**：点「一键安装到已勾选项」。也可点「选择自定义目录安装…」直接装到任意目录（不依赖 Agent 检测）。安装期间按钮禁用、进度条推进，结束后结果区按 `[OK] / [UPDATE] / [UNCHANGED] / [SKIP] / [ERR]` 着色输出明细与「成功 N / 跳过 M / 失败 K」汇总。

界面实测截图：[gui_screenshot.png](<C:\Users\2013083\AppData\Roaming\Tencent\Marvis\User\oAN1i2a0fVAITIdl93aRLTkg_DYY\workspace\conv_98ebfacfe330491d91792ce5ac9c282c\output\photo-mole-installer\dist\gui_screenshot.png>)

---

## 3. CLI 用法（同一 exe，便于脚本化 / 批量部署）

```powershell
# 列出全部 Agent 及检测状态（纯文本，退出码 0）
.\photo-mole-game-installer.exe --cli --list

# 安装到全部「已检测」的 Agent（--yes 跳过交互确认）
.\photo-mole-game-installer.exe --cli --install --all --yes

# 只装到指定 Agent
.\photo-mole-game-installer.exe --cli --install --agents claude-code,cursor --yes

# 装到自定义目录
.\photo-mole-game-installer.exe --cli --install --dest "D:\my-skills" --yes

# 已存在时不覆盖（默认是覆盖并备份）
.\photo-mole-game-installer.exe --cli --install --dest "D:\my-skills" --yes --no-overwrite
```

| 参数 | 说明 |
| --- | --- |
| `--cli` | 进入命令行模式（不带 `--cli` 且无参数时启动 GUI） |
| `--list` | 打印 Agent 检测表后退出 |
| `--install` | 执行安装 |
| `--all` | 目标为全部已检测 Agent |
| `--agents a,b` | 指定 agent key（逗号分隔，未知 key 直接报错退出） |
| `--dest DIR` | 安装到指定目录（与 `--agents` 互斥优先级更高） |
| `--yes` | 免交互确认 |
| `--no-overwrite` | 已存在时记为 `[SKIP]`，不覆盖不备份 |

退出码：`0` 至少一项成功或全部无需变更；`1` 存在失败项或参数非法。

> exe 是 `--windowed` 构建，CLI 输出会同时写入 `%TEMP%\photo-mole-installer.log`（UTF-8，含时间戳），排障时可直接查看该文件。若终端中文显示异常，可先 `chcp 936`，或设置环境变量 `PHOTO_MOLE_OUT_ENCODING=utf-8`。

---

## 4. 支持的 Agent 与默认安装目录（31 项）

| 显示名 | agent key | 默认目标目录（`~` = 用户主目录） |
| --- | --- | --- |
| Amp | `amp` | `~\.config\agents\skills\photo-mole-game` |
| Antigravity | `antigravity` | `~\.gemini\antigravity\skills\photo-mole-game` |
| Claude Code | `claude-code` | `~\.claude\skills\photo-mole-game` |
| Clawdbot | `clawdbot` | `~\.clawdbot\skills\photo-mole-game` |
| Cline | `cline` | `~\.cline\skills\photo-mole-game` |
| CodeBuddy | `codebuddy` | `~\.codebuddy\skills\photo-mole-game` |
| Codex | `codex` | `~\.codex\skills\photo-mole-game` |
| Command Code | `command-code` | `~\.commandcode\skills\photo-mole-game` |
| Cursor | `cursor` | `~\.cursor\skills\photo-mole-game` |
| DeepSeek Harness | `deepseek-harness` | `~\.dsh\skills\photo-mole-game`（也识别 `~/.dsh` 与项目内 `.dsh`） |
| Droid | `droid` | `~\.factory\skills\photo-mole-game` |
| Gemini CLI | `gemini-cli` | `~\.gemini\skills\photo-mole-game` |
| GitHub Copilot | `github-copilot` | `~\.copilot\skills\photo-mole-game` |
| Goose | `goose` | `~\.config\goose\skills\photo-mole-game` |
| Kilo Code | `kilo` | `~\.kilocode\skills\photo-mole-game` |
| Kimi | `kimi` | `~\.kimi\skills\photo-mole-game`（Kimi Code CLI 亦可用 `--skills-dir` 指向该目录） |
| Kiro CLI | `kiro-cli` | `~\.kiro\skills\photo-mole-game` |
| MCPJam | `mcpjam` | `~\.mcpjam\skills\photo-mole-game` |
| Neovate | `neovate` | `~\.neovate\skills\photo-mole-game` |
| OpenCode | `opencode` | `~\.config\opencode\skills\photo-mole-game` |
| OpenHands | `openhands` | `~\.openhands\skills\photo-mole-game` |
| Pi | `pi` | `~\.pi\agent\skills\photo-mole-game` |
| Qoder | `qoder` | `~\.qoder\skills\photo-mole-game` |
| Qwen Code | `qwen-code` | `~\.qwen\skills\photo-mole-game` |
| Roo Code | `roo` | `~\.roo\skills\photo-mole-game` |
| Trae | `trae` | `~\.trae\skills\photo-mole-game` |
| Windsurf | `windsurf` | `~\.codeium\windsurf\skills\photo-mole-game` |
| Zencoder | `zencoder` | `~\.zencoder\skills\photo-mole-game` |
| WorkBuddy | `workbuddy` | `~\.workbuddy\skills\photo-mole-game` |
| 通用互操作目录 | `agents` | `~\.agents\skills\photo-mole-game` |
| 豆包工作（手动导入） | `doubao` | 导出到 `~\photo-mole-game-import`（应用侧技能目录不直接写入，见下方说明） |

**检测判定**：目标 Agent 的配置根目录（如 `~\.claude`）存在即视为「已检测」；若 `…\skills\photo-mole-game\SKILL.md` 已存在，则读出其中 `version:` 显示为「已装版本」。

**豆包工作（`doubao`）走手动导入分支**：其技能位于 `%LOCALAPPDATA%\Doubao\User Data\Default\.doubao\agent_mode\workspace\.skills`，由应用自身管理工作区，安装器不直接写入应用目录（避免应用升级/退出时被覆盖或损坏）。选中 `doubao` 时会把技能包导出到 `~\photo-mole-game-import`，内含：

- `photo-mole-game\`：完整技能目录（19 个文件），可直接复制进 `.skills` 或打包导入；
- `photo-mole-game_v1.3.0.zip`：与 Release 同源的技能包，供应用内「导入技能」使用；
- `豆包工作-手动导入指引.md`：分步操作说明（打开工作区 → 技能管理 → 导入 zip → 校验 `version: 1.3.0`）。

---

## 5. 安装策略与安全边界

- **幂等**：目标已存在时逐文件比对 SHA256；全部一致 → `[UNCHANGED]`，不写盘、不备份。
- **覆盖前备份**：内容有差异且勾选了覆盖 → 先把原目录整体改名为 `photo-mole-game.bak-YYYYMMDD-HHMMSS`，再写入新版本；写入中途失败会自动回滚回备份目录。
- **不覆盖模式**：`--no-overwrite` 或取消勾选时，已存在则记 `[SKIP]`。
- **内容纯净**：打包与安装均排除 `__pycache__`、`*.pyc`、`.DS_Store`，实装 19 个文件。
- **系统目录保护**：拒绝写入 `C:\Windows`、`C:\Program Files`、`C:\Program Files (x86)`、`C:\ProgramData` 及其子目录，命中直接 `[ERR]` 并以退出码 1 结束。
- **单条失败不中断**：某个 Agent 失败只记 `[ERR]`，继续处理其余条目，最后统一汇总。
- **卸载**：直接删除对应 `…\skills\photo-mole-game` 目录即可；若曾覆盖安装，请一并删除同级的 `photo-mole-game.bak-*` 备份目录。

---

## 6. 重新构建

前置：Python 3.11（含 tkinter）+ `pip install pyinstaller`。

```powershell
# 默认自动查找载荷：.\payload\photo-mole-game → ..\backup\photo-mole-game_v1.3.0 → ~\.workbuddy\skills\photo-mole-game → ..\photo-mole-game
powershell -ExecutionPolicy Bypass -File .\build.ps1

# 指定载荷目录
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Payload "D:\path\to\photo-mole-game"
```

也可双击 `build.bat`。脚本会打印 Python / PyInstaller / tkinter 版本、载荷文件数与总字节，构建完成后输出 exe 路径、体积与 SHA256。产物固定为 `dist\photo-mole-game-installer.exe`。

---

## 7. 验收实测结果（v1.3.0，全部基于最终 exe）

测试机：Windows 10 19045 x64，Python 3.11.8，PyInstaller 6.22.3，tkinter 8.6。

| # | 验收项 | 结果 | 实测数据 |
| --- | --- | --- | --- |
| 1 | exe 构建成功 | 通过 | `output\dist\photo-mole-game-installer.exe`，10,436,783 字节（9.95 MB），SHA256 `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A`，载荷 19 文件 / 408,571 字节 |
| 2 | `exe --cli --list` 输出 31 条 + 检测状态 | 通过 | 31/31 条目齐全（新增 DeepSeek Harness / Kimi / 豆包工作），汇总「共 31 个 Agent，已检测 7 个，未检测 24 个」，退出码 0；WorkBuddy 行显示已装 `v1.3.0` |
| 3 | 临时目录真实安装并确认关键文件 | 通过 | `--agents workbuddy --dest <temp>` → 19 文件 / 408,571 字节，含 `scripts\cutout.py`、`scripts\identity.py`、`assets\game_template.html`，无 `__pycache__`、无 `.pyc`，`version: 1.3.0` |
| 4 | 重复执行幂等 | 通过 | `[UNCHANGED] 已是最新（v1.3.0）`，成功 0 / 跳过 1 / 失败 0，未生成 `.bak-*` |
| 5 | 篡改后覆盖 + 自动备份 | 通过 | 追加 `TAMPER_MARK_X` 后重跑 → `[UPDATE]`，生成 `photo-mole-game.bak-20261119-175450`，覆盖后篡改标记清除 |
| 6 | 豆包工作走手动导入分支 | 通过 | `[OK] 手动导入：已导出 …\photo-mole-game（v1.3.0）`，导出目录含技能目录 + `photo-mole-game_v1.3.0.zip` + `豆包工作-手动导入指引.md`，退出码 0 |
| 7 | 无参数启动 GUI | 通过 | 窗口标题 `photo-mole-game 技能一键安装器 v1.3.0`，从启动到窗口出现 1.07 秒；`CloseMainWindow` 后进程退出，无残留 |
| 8 | 系统保护目录拒绝 | 通过 | `--dest "C:\Program Files\pmfail"` → `[ERR] 目标目录位于系统受保护位置，已拒绝`，退出码 1 |
| 9 | 非法 agent key 拒绝 | 通过 | `--agents no-such` → `[ERR] 未知的 agent key: no-such`，退出码 1 |

补充：CLI 全程写入 `%TEMP%\photo-mole-installer.log`（UTF-8，含时间戳与载荷文件数），可据此复盘每次操作。

---

## 8. 已知限制

## 8. 已知限制

- 仅支持 Windows；GUI 依赖系统自带的 Tk（Win10/11 内置，无需额外安装）。
- 首次启动 exe 需解包到 `%TEMP%\_MEIxxxx`，冷启动约 2–4 秒属正常；部分杀软对 PyInstaller 单文件 exe 会误报，可加白名单或改用 `--onedir` 构建。
- Agent 检测以「配置根目录是否存在」为准，若用户把 Agent 装在非常规位置，需用「浏览…」或 `--dest` 手动指定。
- 技能更新到新版本时需重新构建 exe（载荷在构建时嵌入）。
*（内容由AI生成，仅供参考）*
