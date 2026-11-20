# 部署到 WorkBuddy（photo-mole-game v1.3.0）

本技能包是**目录即技能**结构，WorkBuddy 只要在 `~/.workbuddy/skills/` 下看到 `photo-mole-game/SKILL.md` 就会挂载，不需要编译、不需要起服务。

---

## 方式一：一键脚本（Windows，推荐）

解压后在本目录里执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本做的事：定位 `%USERPROFILE%\.workbuddy\skills\`（不存在就建）→ 已有旧版先备份成 `photo-mole-game.bak-<时间戳>` → 复制整包 → 校验 `SKILL.md` 的 frontmatter（`name` / `version`）→ 打印结果。

常用参数：

```powershell
.\install.ps1 -Target "D:\其他\skills"   # 装到别的位置（如多开环境）
.\install.ps1 -Force                     # 跳过"目录已存在"的确认，直接覆盖（仍会备份）
.\install.ps1 -DryRun                    # 只看会做什么，不动文件
```

---

## 方式二：手工复制（跨平台，最稳）

```bash
# 1) 找到 skills 目录
#    Windows: C:\Users\<你>\.workbuddy\skills
#    macOS/Linux: ~/.workbuddy/skills
mkdir -p ~/.workbuddy/skills

# 2) 整包复制（目录名必须是 photo-mole-game）
cp -r photo-mole-game ~/.workbuddy/skills/

# 3) 验证 frontmatter 里 version 是 1.3.0
head -20 ~/.workbuddy/skills/photo-mole-game/SKILL.md
```

复制后重启 WorkBuddy（或在技能面板点刷新），在技能列表里应能看到「照片打地鼠游戏生成器」。

---

## 方式三：压缩包直挂

把 `photo-mole-game_v1.3.0.zip` 拖进 WorkBuddy 的技能安装入口（若有"从文件安装技能"功能），包的**根目录就是 `photo-mole-game/`**，解开后即为合法技能目录。

> 注意：不要把文件平铺到 `skills/` 根下，`skills/photo-mole-game/SKILL.md` 这一层不能少。

---

## 装完怎么验

```bash
# 1) 依赖（首次）
pip install pillow numpy opencv-python

# 2) 门禁脚本能跑（v1.3 起是四道门禁）
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --file /tmp/g.json --show
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --help | grep -i identity

# 3) 拼图脚本能跑（随便给两张图）
python ~/.workbuddy/skills/photo-mole-game/scripts/make_sheet.py --in /tmp --out /tmp/sheet.jpg

# 4) 抠图脚本的 v1.3 新能力在（--analyze / --verify / --compare）
python ~/.workbuddy/skills/photo-mole-game/scripts/cutout.py --help | grep -E "analyze|verify|compare"

# 5) 身份脚本能出骨架（v1.3 新增，决定卡通像不像本人）
python ~/.workbuddy/skills/photo-mole-game/scripts/identity.py --template --out /tmp/features.json

# 6) 构建脚本存在门禁校验
python ~/.workbuddy/skills/photo-mole-game/scripts/build_game.py --help | grep -i gate
```

六步都不报错，说明包是完整的。

---

## 升级与回滚

- **升级**：新版解压后重跑 `install.ps1`，脚本会先把旧的备份为 `photo-mole-game.bak-<时间戳>`，再把新的放进去。
- **回滚**：删掉新版目录，把备份目录改回 `photo-mole-game` 即可。
- **版本确认**：`SKILL.md` frontmatter 的 `version` + `manifest.json` 的 `version` 两处应一致；`manifest.json` 里带每个文件的 sha256，怀疑包被改动过半时用它核对。

---

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 技能列表里看不到 | 目录层级不对（少了 `photo-mole-game/` 这层），或 `SKILL.md` frontmatter 被破坏 | 检查路径与文件头 YAML |
| 技能能挂载但不出图 | 本地 sd-server 没起 | 先 `--manifest-only` 导 prompt 清单，或启动 `127.0.0.1:8790` |
| `build_game.py` 报"门禁未通过" | 正常拦截，照片/表情/惊喜图/身份相似度四项确认没走完 | `gate.py --show` 看缺口，问完用户再写 |
| `build_game.py` 报"缺 cutout.report.json"或"有 FAIL" | 阶段 B 没跑 `--verify`，或抠图吞了主体 | 补跑 `cutout.py --verify`，FAIL 项回阶段 A 重生 |
| 卡通出来不像本人 | 没做阶段 A0 特征分析，或用了通用动漫脸 | 走 `identity.py --template/--validate/--emit` → `gen_expressions.py --features` 重出，再做 `--compare-sheet` 评分 |
| 提示缺 `cv2` / `PIL` | 依赖没装 | `pip install pillow numpy opencv-python` |
| 中文变问号 | 终端编码不是 UTF-8 | `chcp 65001`（PowerShell 用 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`） |
