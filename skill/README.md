---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_d2e1ff31e22511f1a768525400cd780f
    ReservedCode1: xfgXmJmRTBkEDAYSSRU3pBGmym7xNugZ3hI1uo076R296RwKUOdGnBI9GXc6lvkyYQT/SBcUuSfIFd3RKiXhW8HfZBQEa72lM4r2IpeLt3E76rY5N15miVUI93GJpoX64OkF2+qv88BZtQR75l8Fn2TrDGTWZ3BjE16w54QdtJYK/U7QIyGTElI9liA=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_d2e1ff31e22511f1a768525400cd780f
    ReservedCode2: xfgXmJmRTBkEDAYSSRU3pBGmym7xNugZ3hI1uo076R296RwKUOdGnBI9GXc6lvkyYQT/SBcUuSfIFd3RKiXhW8HfZBQEa72lM4r2IpeLt3E76rY5N15miVUI93GJpoX64OkF2+qv88BZtQR75l8Fn2TrDGTWZ3BjE16w54QdtJYK/U7QIyGTElI9liA=
---

# photo-mole-game · 照片变打地鼠小游戏

给 agent 用的技能包：**一张照片 → 一个带本人卡通形象、可离线玩的打地鼠 HTML 游戏**。

整套流程在「敲谈姐儿 v1.4.0」上完整跑通并回归验证（4 档 / 15 关 / 11 表情 / 8.3 MB 单文件版），现已固化为四条脚本的流水线。

---

## 安装（3 种方式）

```powershell
# Windows 一键（推荐）
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
或手工把整个 `photo-mole-game/` 目录复制到 `%USERPROFILE%\.workbuddy\skills\`（macOS/Linux 为 `~/.workbuddy/skills/`），重启 WorkBuddy 即可在技能列表看到「照片打地鼠游戏生成器」。详见 `INSTALL.md`。

## 快速上手（6 步）

```bash
# 0. 依赖
pip install pillow numpy opencv-python playwright

# 1. 出表情原图（本地引擎；没有引擎就加 --manifest-only 走 MCP / 线上模型）
python scripts/gen_expressions.py --photo me.jpg --out raw/ \
    --endpoint http://127.0.0.1:8790 --desc "cute young woman, short hair, glasses"

# 2. 小样给用户看 → 三选一确认后写真门禁（v1.1 硬环节，不许跳过）
python scripts/make_sheet.py --in raw --out raw/sheet.jpg --cols 4 --title "表情小样：全部通过 / 全部重做 / 指定重做？"
python scripts/gate.py --file gate.json --expressions all_pass --sheet raw/sheet.jpg --quote "全部通过"

# 3. 抠图 + 统一画布
python scripts/cutout.py --in raw/ --out assets/ --normalize

# 4. 惊喜图（先问来源与文字，再落门禁）
python scripts/gen_prize.py --mode ai --init assets/normal.png --out prize --poses 3 \
    --endpoint http://127.0.0.1:8790 --text "请喝咖啡"
python scripts/gen_prize.py --pick prize/prize_pose2.png --out prize --text "请喝咖啡"
python scripts/gate.py --file gate.json --prize ai_generated --poses 3 \
    --pick prize/prize_pose2.png --text "请喝咖啡" --text-source user --quote "用第二张"

# 5. 按你的主题改 config（抄 examples/ 里的一份改）
cp examples/config.minimal.json config.json

# 6. 构建 + 交付前回归
python scripts/build_game.py --config config.json --assets assets/ --out dist/ --gate gate.json --single
python scripts/verify_game.py --dir dist/ --config config.json --out verify.json
#    → 期望输出 {"errs": [], ...}
```

> `gate.json` 里必须齐三项：照片来源（用户明确给的）、表情小样（用户三选一过的）、惊喜图（来源+文字确认过的）。缺任何一项，`build_game.py` 拒绝构建——这是 v1.1 防止"替用户做决定"的核心约束。

## 目录结构

```
photo-mole-game/
├── SKILL.md                     操作手册（agent 主入口，含需求收集表与三条红线）
├── README.md                    本文件
├── INSTALL.md                   部署到 WorkBuddy 的三种方式
├── manifest.json                技能包元信息（版本 / 文件清单 / sha256）
├── install.ps1                  Windows 一键安装脚本
├── assets/game_template.html    游戏模板（CONFIG 占位符，勿手改逻辑）
├── scripts/
│   ├── gate.py                  三关确认门禁（写 gate.json）
│   ├── gen_expressions.py       表情批量出图 / prompt 清单导出
│   ├── make_sheet.py            小样拼图（给用户看/挑）
│   ├── cutout.py                抠图 + 统一画布
│   ├── gen_prize.py             惊喜图：上传入库 / 全身多姿势生成 / 叠字
│   ├── build_game.py            构建目录版 + 单文件版（含门禁校验）
│   └── verify_game.py           Playwright + CDP 无头回归
├── examples/
│   ├── config.qiaotan.json      v1.4 原版 4 档配置
│   └── config.minimal.json      3 档最小示例
└── references/
    ├── config-schema.md         config 全字段
    ├── expressions.md           11 表情 + 提示词配方 + 参数表
    └── pitfalls.md              17 条踩坑 + GitHub 发布流程
```

## 可自定义项

主题名 / 副标题 / 引导语 / 形象自称 / 难度档数与命名 / 每档关数 / 命数 / 加命上限 / 金蛋彩蛋奖励值 / 彩蛋页文案与 emoji / 惊喜图（用户上传，或系统生成全身卡通多姿势 + 图上文字）/ 表情数量（≥6）/ 评分档位文案 / 玩法说明。

全部落在 `config.json`，改完重跑 build + verify 即可，无需碰模板。

## 版本

| 版本 | 要点 |
| --- | --- |
| **v1.1.0**（2026-11-18） | 三道硬门禁（照片来源 / 表情小样三选一 / 惊喜图来源与文字）；新增 `gate.py`、`make_sheet.py`、`gen_prize.py`；`build_game.py` 构建前校验 gate.json；补安装脚本与 manifest，支持一键部署 |
| v1.0.0 | 首次部署版：表情生成 + 抠图 + 构建 + 回归四段流水线 |

v1.1.0 修的是实测暴露的"该问却没问"：照片来源选完没等用户交付就自行搜图库、表情小样三选一流程缺失、惊喜图该让用户上传却由 skill 直接生成且不问文字。现在这三件事都变成脚本级约束（见 SKILL.md §0.5 三条红线）。

## 已验证

| 配置 | 结果 |
| --- | --- |
| `examples/config.qiaotan.json`（4 档 9/9/12/15 关） | 目录版 98,125 B + 单文件版 6,861,251 B，校验 errs = `[]` |
| `examples/config.minimal.json`（3 档 3/6/9 关） | 目录版 97,375 B + 单文件版 6,860,501 B，校验 errs = `[]` |

校验覆盖：JS 异常、标题/眉标/版本号、难度卡片文案、`#maxLvl`、开局态、11 张表情加载、彩蛋页四档文案与头像、纸屑像素、3 秒按钮延时、单文件版零外部引用。

## 版权与署名

游戏产物默认署名规则按项目另定；本示例出处「敲谈姐儿 v1.4.0」，仓库 `jaja1620/qiaotan-jieer`。
*（内容由AI生成，仅供参考）*
