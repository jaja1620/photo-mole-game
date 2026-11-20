---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_06abbad5e2e611f1b140525400de85a5
    ReservedCode1: iOxa0aWGZ6QN3XGyIZjHg9zyOoPFjegm1J9f8dKn+kj4fVi7kC6+Tt8bSsdni+uZth/iASCXmAV8HOEc5SRnrowxwkKW17WDSpiqty7Khck8DZ/Dc+oodIypkpZ/zCpdnjdDMa01fFngPIN05v3AO0/pJk+5iwEFAzamxz+RavRA0i8M8oAWTiaW0sQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_06abbad5e2e611f1b140525400de85a5
    ReservedCode2: iOxa0aWGZ6QN3XGyIZjHg9zyOoPFjegm1J9f8dKn+kj4fVi7kC6+Tt8bSsdni+uZth/iASCXmAV8HOEc5SRnrowxwkKW17WDSpiqty7Khck8DZ/Dc+oodIypkpZ/zCpdnjdDMa01fFngPIN05v3AO0/pJk+5iwEFAzamxz+RavRA0i8M8oAWTiaW0sQ=
name: photo-mole-game
display_name: 照片打地鼠游戏生成器
description: Turn one photo into an offline single-file whack-a-mole HTML game where the mole is the user's own cartoon avatar. Use when the user asks to make a whack-a-mole / 敲小人 / 打地鼠 game from a photo, or to change an existing one.
description_zh: 把一张照片变成可离线运行的单文件打地鼠小游戏，游戏里的地鼠是照片主人的卡通形象。用于「用我的照片做个打地鼠/敲小人游戏」「换张照片重做」等需求。
description_en: Photo-to-whack-a-mole HTML game generator: cartoon avatar expressions, cutout, config, single-file build and headless regression verification.
version: 1.3.0
author: JaJa
allowed-tools: Bash Read Write Edit Glob Grep AskUserQuestion
visibility: public
---



## 路径与运行约定（先读）

- 本 skill 的根目录记为 `{baseDir}`，下文的 `scripts/`、`assets/`、`references/`、`examples/` 都相对它。
- 命令里的脚本一律用 `{baseDir}/scripts/xxx.py` 调用；**运行目录不要求是 skill 根目录**，脚本内部用 `__file__` 定位 `assets/game_template.html`，可移植。
- 用户产物（照片、raw/、assets/、dist/、config.json、verify.json）**不要写进 skill 目录**，统一放在当前会话工作目录 `work/<主题名>/` 下。
- 依赖：Python 3.11 + `pillow numpy opencv-python`，校验阶段另需 Playwright 与本机 Edge。缺包先 `pip install` 再重试。

# 照片 → 卡通打地鼠游戏（photo-mole-game）

把「一张照片」变成「一个可离线运行的单文件 HTML 打地鼠游戏」，游戏里的地鼠是用户本人的卡通形象，会笑、会痛、会求饶。

整套流程已在「敲谈姐儿 v1.4.0」上完整跑通并回归验证，本 skill 把它固化为可复用流水线。

---

## 0. 何时用这个 skill

用户说这些话就用：

- 「用我的照片做个打地鼠游戏」「给我整一个敲一敲小游戏」
- 「把上次那个打地鼠改一改，换成我 / 换成某人」
- 「做个能在手机上玩的小游戏，主角是真人照片」

不适用：需要联网对战、需要后端存档、需要真实物理引擎的项目——本 skill 产出的是**纯前端零依赖单文件**游戏。

---

## 0.5 六条红线（v1.1 立规、v1.2 加固、v1.3 补抠图与相似度，违反即任务失败）

v1.0 实测暴露的问题都出在同一处：**说明书里写了要问，实际却"自我放行"跳过了**。v1.1 起把关键节点做成脚本级硬门禁，`build_game.py` 会检查 `gate.json`，没确认过就**直接拒绝构建**；v1.2 再补两条：小样背景必须纯色可抠、惊喜图必须覆盖每个非轻松难度；v1.3 再补两条：抠图不许吞主体、卡通不许不像本人。

| # | 红线 | 具体要求 | 违反的典型表现 |
| --- | --- | --- | --- |
| 1 | **照片来源必须由用户明确指定** | 先问三选一：①我上传 ②我给你本机路径 ③你从本机图库找几张给我挑。选①/②时**必须停下来等用户交付**，不能自己去找 | 用户选了"由我上传或指定路径"，skill 没等，直接当成"用户没提供"自动检索了图库 |
| 2 | **表情小样必须先给用户看并三选一，背景一律纯色** | 出完 raw/ 用 `make_sheet.py` 拼图（默认带背景检查）发给用户，等明确回复「全部通过 / 全部重做 / 指定重做」；小样背景**只允许 magenta / green / blue / white 四种利于抠图的纯色**，检查 FAIL 的图不许拿给用户"通过"，必须先重生 | 直接跳过确认开始抠图和构建；或小样是渐变/场景背景，抠完白衣服被吃掉、头部一圈花边 |
| 3 | **惊喜图来源与覆盖范围必须先问** | 先问来源（**我上传 / 系统自动生成 / 本地合成**），再问是**所有通关难度共用一张**还是**每个难度各用不同一张**；`gate.py --prize` 必须带 `--scope same\|per_diff` | 说明里写了可上传，实际直接由 skill 生成，也没问过文字和是否每档不同 |
| 4 | **除「轻松」外的每个难度通关后都要有惊喜图** | `easy` 不配惊喜图（通关只弹彩蛋页）；`normal / hard / hell` 每档都必须有定案图，缺一档 `build_game.py` 直接报错 | 只写了 `byDiff.default` 一张，轻松难度也弹同一张，用户"轻松通关就看到惊喜"完全没有铺垫 |
| 5 | **抠图禁止吞掉主体、衣服、配件；抠前必须分析参数，抠后必须比对** | 跑 `cutout.py` 前先 `--analyze` 看背景一致度/主体占比并据此定 `--tol`/`--bg-hex`，同时肉眼看原图判断哪些部件颜色接近背景（白衬衫白底、黑发压深色底、眼镜片、耳饰）；抠图默认开主体保护，抠完必须 `--verify` 出 `cutout.report.json` + `--compare` 出对照图，人完整了才许进构建 | 抠完白衣服变透明、眼镜没了、头边一圈紫边、耳饰消失；或者不看报告直接进构建，交付后用户第一眼就看到"人少了半个" |
| 6 | **卡通必须基于真人特征分析，且相似度达标** | 出图前先按 §2.5 阶段 A0 用图像理解逐字段分析照片，产出特征 JSON（`identity.py --template` → 填 → `--validate`）与中文特征总结交用户确认；出图后用 `identity.py --compare-sheet` 做原图/卡通对照并评分，写身份门禁；评分 <65 返工，65~79 按差异点改特征重出，≥80 才能拿去让用户确认 | 直接拿照片 img2img 出一套"通用动漫脸"，用户第一反应"这不像我"；或者自己说"挺像的"就往下走，没有任何对照与评分留痕 |

落地手段：每次拿到用户回复后，**立刻**用 `gate.py` 写一笔（带用户原话 `--quote`），不要攒到最后补：

```bash
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json --show          # 随时看缺口
```

`--quote` 必须逐字引用用户原话，**禁止自己编一句话充数**。没有用户回复就不要写门禁，宁可停下来问。

---

## 1. 先收需求（这一步别跳）

开工前把下面这张表填掉。**必填项缺任何一项都要问用户**；选填项缺失就用默认值直接往下走，不要卡在追问上。

### 必填

| 输入 | 说明 | 示例 |
| --- | --- | --- |
| **照片（必须先问来源）** | 正面清晰人像，脸部无遮挡，最好纯色或简单背景。**不许自己默认去搜图库**，见下方 §1.1 | `me.jpg` |
| 主题名称 | 游戏标题，出现在菜单、页面 title、文件名 | 敲谈姐儿 |

### 1.1 照片三选一（硬门禁，不要抢答）

用 `ask_user`（单选）问，选项固定三项：

| 选项 | 用户选后你要做什么 |
| --- | --- |
| **① 我上传** | **停下**，等用户把图片发过来（拿到落盘路径）。返回"我先看看你电脑里的图"是错的 |
| **② 我给你路径** | **停下**，等用户给出目录或文件名。拿到后先确认路径真实存在（`os.path.exists`），不存在就问，不要自己换一个 |
| **③ 你帮我找几张** | 这时才允许检索本机图库：取最近的照片/相册目录，挑 4~8 张面部清晰的，**列成候选让用户挑**，禁止直接采用任何一张 |

用户选了①或②却没有下文时，正确动作是**再问一次**（「照片方便发我一下吗？或者把路径贴给我」），不是"那我自己找找"。

拿到照片后立刻写门禁：

```bash
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json \
    --photo "D:/照片/me.jpg" --source user_upload --quote "用我上传的这张"
# source 取值：user_upload（用户上传）/ user_path（用户给路径）/ user_picked（从候选里挑，此时补 --candidates 列候选路径）
```

### 选填（带默认值）

| 输入 | 默认值 | 说明 |
| --- | --- | --- |
| 副标题 | 办公室解压小游戏 | 标题下方小字 |
| Kicker 眉标 | `Office Arcade · No.01` | 菜单顶部小标签 |
| 引导语 | 自动生成 | 菜单一句话 |
| 形象自称 / 人称 | `她` | 彩蛋文案里怎么称呼主角 |
| 难度档数 | 4 档（轻松/普通/困难/地狱） | 可减到 2~3 档，也可改名 |
| 每档关数 | 9 / 9 / 12 / 15 | 决定通关长度 |
| 每档命数 | 15 / 10 / 8 / 6 | 初始命 |
| 加命上限 | 无上限 / 20 / 12 / 10 | 金蛋彩蛋能加到多少 |
| 金蛋 / 彩蛋奖励 | +1 命 / +2 命（命满折 50 / 100 分） | 可改成 +2/+3 |
| 彩蛋页文案 | 自动生成 | 通关后那段话，可含 `<mark>` 高亮 |
| **惊喜图（必须先问来源 + 覆盖范围）** | 先问再定：来源三选一（我上传 / 系统自动生成 / 本地合成），覆盖范围二选一（所有通关难度共用一张 / 每个难度各一张），图上文字也要问，见 §5.5 |
| 表情数量 | 11 张 | 可减少（最少建议 6 张），见 §3 |
| 形象要求 | 无 | 「戴眼镜」「丸子头」「穿白大褂」等，会写进提示词 |
| 出图路线 | 本地优先 | 本地 locmodel/flux.2 或线上图片转卡通 |

> 交互原则：**一次性把这张表发给用户**，让用户勾掉/补全，而不是一问一答挤牙膏。用户说「你看着办」时全部用默认值。

---

## 2. 流水线总览

```
[0] 门禁确认（gate.json）── ① 照片来源  ② 真人特征分析 + 卡通相似度（v1.3）
                         ③ 表情小样三选一（背景纯色）  ④ 惊喜图来源+覆盖范围+文字
        │  任一项未确认，build_game.py 拒绝构建
        ▼
照片 ─┬─► [阶段A0] 真人面部特征分析 ─► work/<主题名>/features.json（v1.3，必做）
      │        （图像理解逐字段分析 → 中文特征总结交用户确认）
      ▼
      [阶段A] 卡通形象生成 ─► raw/*.png（纯色底）─► [阶段B] 抠图归一化 ─► assets/*.png
      │      （11 张表情，两条路线；--features 写入身份锁定词）  （抠前分析 → 定参 → 抠图 → 抠后比对）
      │
      ├─► [阶段P] 惊喜图（上传 / 系统生成 / 本地合成；共用一张或每档各一张）─► prize/prize*.jpg
      ▼
   [阶段C] 配置 config.json ─► [阶段D] 构建 ─► 目录版 index.html + 单文件版 .html
                                             └─► [阶段E] 无头回归校验 ─► [阶段F] 交付
```

脚本各管一段，**不要绕过脚本手搓 HTML**：

| 脚本 | 职责 |
| --- | --- |
| `scripts/identity.py` | **（v1.3）真人面部特征**：`--template` 出特征 JSON 骨架、`--validate` 校验必填、`--emit` 出英文 desc 与身份锁定词、`--compare-sheet` 出原图/卡通对照并按权重评分 |
| `scripts/gate.py` | **（v1.1 三关 / v1.3 四道门禁，含身份相似度）确认留痕**，写 gate.json；`--show` 随时查缺口 |
| `scripts/gen_expressions.py` | 批量出表情原图（**纯色背景，默认 magenta**），或导出 prompt 清单供 MCP / 线上模型执行；**（v1.3）`--features` 把真人特征写进 desc 与身份锁定词** |
| `scripts/make_sheet.py` | **（v1.1）小样拼图**；**（v1.2）默认附带背景检查** `bgcheck.json`，是写门禁的前置条件 |
| `scripts/cutout.py` | 抠图 + 统一画布（色度键优先，读 manifest 里记录的背景色）；**（v1.3）`--analyze` 抠前分析、默认主体保护、`--verify` 抠后比对出 `cutout.report.json`、`--compare` 出对照图** |
| `scripts/gen_prize.py` | **（v1.1）惊喜图**：用户图入库、系统生成全身多姿势、叠文字；**（v1.2）新增 `--mode compose` 本地合成多版式供挑选** |
| `scripts/build_game.py` | 吃 config.json + assets/，产出目录版与单文件版（**构建前校验 gate.json 四道门禁 + `cutout.report.json` 无 FAIL**；按 `scope` 给各难度铺惊喜图） |
| `scripts/verify_game.py` | Playwright + CDP 连接本机 Edge，双形态回归校验 |

`assets/game_template.html` 是模板，所有可变内容已抽成 `__MOLE_CONFIG__` 占位符，**改需求改 config，不改模板**。

---

## 2.5 阶段 A0：真人面部特征分析（v1.3 必做，红线 6）

出任何卡通图之前先做人脸特征分析，把"像不像"从手感变成可核对的数据。**跳过这一步就是红线 6 违规**：表情图已经按错的模板出了一整轮，再补等于整轮白做。

### A0.1 看图（图像理解，不许凭印象猜）

用图像理解工具（`analyze_image` 或平台自带读图能力）看用户照片，按下面字段逐项判定，**只写看得见的，看不清就留空等用户补**：

| 字段 | json key | 取值示例 |
| --- | --- | --- |
| 脸型 | `face_shape` | round / oval / square / long / heart |
| 肤色 | `skin_tone` | fair / light / medium / tan |
| 发长 | `hair_length` | short / shoulder / long |
| 分缝 | `hair_parting` | middle / side_left / side_right / none |
| 发色 | `hair_color` | black / dark_brown / brown / blonde |
| 发质卷度 | `hair_texture` | straight / wavy / curly |
| 刘海 | `bangs` | none / straight / side_swept / airy |
| 眉 | `eyebrows` | thick_straight / thin_arched / soft |
| 眼睛 | `eyes` | big_round / almond / monolid / double_lid，另记瞳色与睫毛 |
| 眼镜 | `glasses` | none / thin_metal_round / thick_black_square（含镜片色） |
| 鼻 | `nose` | small_button / straight / broad |
| 嘴/唇 | `mouth` | thin_lips / full_lips，另记唇色 |
| 耳 | `ears` | visible / covered_by_hair |
| 特殊标记 | `marks` | 痣、纹、胡须、妆容，按位置描述 |
| 配件 | `accessories` | 耳饰、项链、发饰（颜色 + 样式） |
| 服装 | `clothing` | 领型 + 主色 + 图案，如 white crew-neck tee |
| 年龄感 | `age_feel` | 20s / 30s / … |
| 一句话辨识点 | `distinctive` | 最能把这个人跟别人区分开的 1~2 个特征 |

**顺手记一件事**：照片里哪些部件颜色接近背景（白衬衫撞白底、黑发压深色底、银色镜框、浅色耳饰）——到阶段 B 定参数时要用这份判断。

### A0.2 产出特征 JSON

```bash
# 1) 出骨架（必填项留空待填）
python {baseDir}/scripts/identity.py --template --features work/<主题名>/features.json

# 2) 按 A0.1 的观察把字段填进去（编辑 JSON，不要删字段）

# 3) 校验必填齐备（缺项会逐条列出，不齐不许往下走）
python {baseDir}/scripts/identity.py --validate --features work/<主题名>/features.json

# 4) 出英文 desc 与身份锁定词（后面 gen_expressions.py --features 会直接读它）
python {baseDir}/scripts/identity.py --emit --features work/<主题名>/features.json
```

必填 11 项：`face_shape / skin_tone / hair_length / hair_color / bangs / eyes / eyebrows / nose / mouth / glasses / clothing`。`--validate` 报缺就回去补看或问用户，**不要编个值糊过去**。

### A0.3 中文特征总结，请用户确认

把 JSON 翻成一段人能读的中文（5~8 行）发给用户，例如：

```
我从照片里看到：圆脸、偏白肤色、齐耳短发偏分、黑发、空气刘海；内双、眼睛偏圆、睫毛明显；
金属细框圆眼镜；鼻头小巧；薄唇偏粉；耳侧没看到耳饰；白色圆领 T 恤；整体 20 多岁；
最好认的是左眉尾一颗小痣。
按这个形象做卡通，行吗？哪里不对直接说（比如眼镜其实是黑框），我改完再出图。
```

用户确认或给出修正后再进阶段 A。用户改过的要**回写 JSON 并重新 `--validate`**。

### A0.4 出图后做对照 + 评分（红线 6）

第一张卡通图出来（通常先出 `raw/normal.png`）就立刻对照，不合格别扩表情：

```bash
python {baseDir}/scripts/identity.py --compare-sheet \
    --features work/<主题名>/features.json \
    --photo D:/照片/me.jpg --cartoon work/<主题名>/raw/normal.png \
    --out work/<主题名>/identity.compare.jpg --json work/<主题名>/identity.score.json
```

权重：脸型 25 / 发型 25 / 眼睛 15 / 眼镜 15 / 肤色 10 / 服装 10，满分 100。

| 评分 | 判定 | 动作 |
| --- | --- | --- |
| ≥ 80 | PASS | 把对照图 + 评分发用户确认，通过后再扩其余表情 |
| 65 ~ 79 | WARN | 按差异点改特征或 `--extra-prompt` 重出这张，**不许直接进小样** |
| < 65 | FAIL | 视为不像本人，回 A0.1 重新看照片、重写特征重出；脚本退出码 2 |

用户说"不像"时，无论评分多少一律按"不像"处理：问到具体差异（脸太尖 / 眼睛不对 / 眼镜没了 / 发型不符），改特征 → 重出 → 再对照。

拿到用户确认后写身份门禁（缺它 `build_game.py` 直接拒绝构建）：

```bash
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json \
    --identity-features work/<主题名>/features.json \
    --identity-score 86 \
    --identity-compare work/<主题名>/identity.compare.jpg \
    --quote "对对，就这个感觉"
```

评分 <65 时 `gate.py` 直接拒绝写入（exit 1）；65~79 会打印警告并要求先问用户；`--quote` 同样必须逐字引用用户原话。

---

## 3. 阶段 A：卡通形象生成

### 3.1 表情清单（默认 11 张）

游戏按用途把表情分三组，缺组会导致游戏报错或表现呆滞：

| 组 | 用途 | 默认成员 |
| --- | --- | --- |
| `rise` | 从洞里冒出来时随机切换 | normal、01_smug、02_tongue、03_tease、04_taunt、09_disdain |
| `hurt` | 被砸中时的痛苦表情 | 05_angry、06_cry、07_dizzy、10_sad |
| `mock` | 逃跑/嘲讽/彩蛋页 | 04_taunt、09_disdain、02_tongue |

完整清单与中英文描述见 `references/expressions.md`。

**减量规则**：`rise ≥ 2`、`hurt ≥ 2`、`mock ≥ 1`，且 `normal` 必须存在（也充当菜单装饰与结果页头像）。少于 6 张就不建议再做表情系统了。

### 3.2 两条出图路线

#### v1.3 前置：`--features` 必须带上（红线 6）

`--features work/<主题名>/features.json` 是 v1.3 起出图的标准姿势，它会把 A0 产出的真人特征写进三处：`desc`（人物描述由特征拼出，不再是你手写一句）、身份锁定**正向词**（同发型、同眼镜、同脸型、可辨认是本人）、**负向词**扩充（`different person / generic anime face / wrong hairstyle / missing glasses / changed face shape / different hair color / unrecognizable identity`）。不带 `--features` 出的图就是"通用动漫脸"，后面评分必然掉到 65 以下。

```bash
# 带特征的本地批量生成（v1.3 标准写法）
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ \
    --endpoint http://127.0.0.1:8790 \
    --features work/<主题名>/features.json \
    --strength 0.66 --two-stage
```

带着 `--features` 时不用再手写 `--desc`（手写的会被特征 desc 盖掉）；`--extra-prompt` 仍然生效，只用来追加"眼睛再大一点"这类微调。

**路线 1：本地引擎（默认，全自动、离线、免费）**

```bash
# 先看提示词清单
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --desc "cute young woman, short hair, glasses" --list

# 批量生成（照片直接 img2img，一次 11 张）
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ \
    --endpoint http://127.0.0.1:8790 \
    --desc "cute young woman, short hair, glasses" \
    --strength 0.66 --steps 20 --sampler euler --cfg 7.0 --seed 20261112

# 想一致性更高：先出定妆照，再以定妆照为基准扩表情
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ --endpoint ... --two-stage
```

引擎经 locmodel MCP 启动（`locmodel-image` 服务的 `engine_discover` / `load_model`），或直接复用已在跑的 sd-server 端口（默认 `127.0.0.1:8790`）。可用模型里 **flux.2（flux-2-klein-4b）** 与 `z_image_turbo-Q4_K` 均可做 img2img。

#### v1.2 背景色硬规范：一律纯色，为抠图让路

小样背景**不许出现渐变、场景、光晕、投影、道具**——这些都是抠图花边的直接来源（白衬衫被当背景吃掉、头发边缘一圈紫边）。脚本已把这件事做进提示词与默认值：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--bg` | `magenta` | 四选一：`magenta`(#FF00FF) / `green`(#00FF00) / `blue`(#0000FF) / `white`(#FFFFFF) |
| `--bg-hex` | 空 | 自定义纯色 `#RRGGBB`，覆盖 `--bg`（能抠但会判 WARN，非必要不用） |

- 选色规则：**人物身上有紫/粉色衣服 → 换 green；有绿色 → 换 blue；有深色描边 → 可用 white**；其余情况清一色 magenta（与肤色色差最大，最好抠）。
- 正向词已内置 `{bg} background (#HEX), completely uniform fill, no gradient, no vignette, no shadow, no props`；负向词已内置 `gradient background / textured background / scenery / bokeh / drop shadow / props`，**不要自行把这类词删掉**。
- 背景色值会写进 `raw/manifest.json` 的 `bg.hex`，阶段 B 抠图直接读它，不用再手工指定。
- 走 MCP / 线上路线时，`--manifest-only` 导出的清单里每条 prompt 都带同一背景色描述，逐张生成时**照抄 prompt，别自己简化**。

**路线 2：MCP / 线上模型（要更好画风时用）**

```bash
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ --manifest-only
# 产出 raw/manifest.json，里面每个表情都带 prompt / negative / seed
```

然后任选其一执行：

- **locmodel MCP**：`redraw_image(init_image=照片, prompt=清单内 prompt, negative_prompt=清单内 negative_prompt, strength=0.66, seed=清单内 seed)`，逐张存成 `raw/<key>.png`
- **WorkBuddy 的「图片转二次元 / 卡通」skill 或工作流**：把照片和清单里的 prompt 一起喂进去，按 `raw/<key>.png` 命名回传
- **线上文生图模型**：把 prompt 里的 `{desc}` 换成人物描述即可，不传 init_image 也能用，但角色一致性会差一些

### 3.3 小样确认（红线 2：先问再走，禁止自我放行）

原图出来**必须先给用户看小样，再进入抠图**。用脚本拼图，不要口述"我生成了 11 张"就往下走：

```bash
python {baseDir}/scripts/make_sheet.py --in work/<主题名>/raw --out work/<主题名>/raw/sheet.jpg \
    --cols 4 --title "表情小样 11 张：全部通过 / 全部重做 / 指定重做？"
```

把 `sheet.jpg` 发给用户（图 + 一句明确的三选一提问），然后**停下来等回复**。

#### 发图之前先看背景检查（v1.2 硬门禁）

`make_sheet.py` 默认带 `--check-bg`，拼图的同时逐张判背景，终端会打印 PASS / WARN / FAIL，并写出 `sheet.bgcheck.json`；拼图右上角也会印一个背景色块。判定口径：

| 判定 | 含义 | 你的动作 |
| --- | --- | --- |
| **PASS** | 预设纯色（magenta/green/blue/white）且四角一致、背景占比 ≥15% | 可以直接发用户 |
| **WARN** | 纯色但非预设色，或背景占比偏低（人物几乎顶满画面） | 能发，但要说明"这几张背景偏自定义色，抠图可能略毛，建议重生" |
| **FAIL** | 四角颜色不一致（渐变/场景/光斑）或背景占比 <15% | **不许发用户当"可确认"**，先按纯色重生再看一遍 |

FAIL 的处理方式是重生对应 key、不是硬抠：

```bash
# 只重做不合格的那几张，强制纯色底
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ --endpoint http://127.0.0.1:8790 \
    --only b_gradient,xx_other --bg magenta --extra-prompt "plain flat magenta backdrop"

# 重拼小样 + 重新检查
python {baseDir}/scripts/make_sheet.py --in work/<主题名>/raw --out work/<主题名>/raw/sheet.jpg --cols 4
```

若 `sheet.bgcheck.json` 里还有 FAIL，`gate.py --expressions` 会直接拒绝写入（`redo_all` 除外，因为那本来就是全部重做）。三种回复对应的动作：

| 用户回复 | 你的动作 |
| --- | --- |
| **全部通过** | 写门禁 → 进阶段 B |
| **全部重做** | 记下补充意见，`--extra-prompt "..."` 全量重跑，**重跑后再拼小样再问一次**，直到通过 |
| **指定重做** | 用户点名 key，`--only 05_angry,06_cry --extra-prompt "..."` 重跑这几张，**重跑后再拼图再问一次** |

拿到明确回复后写门禁（`--sheet` 指向刚发出去的那张拼图，缺它不认）：

```bash
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json \
    --expressions all_pass --sheet work/<主题名>/raw/sheet.jpg --quote "表情都行，继续"
# 全部重做：--expressions redo_all ；指定重做：--expressions partial --redo 05_angry,06_cry
```

注意：声明 `redo_all` / `partial` 后门禁即视为"已确认"，但**重做完必须重新走一轮小样确认**并把 decision 改回 `all_pass`（或再写一次 partial），否则等于没确认。用户没回话就催一次，不要替他判断"应该差不多能过"。

补充意见要**同时写进 prompt 和 manifest**，保证可复现。常见补充要求及其 prompt 落点：

| 用户说法 | prompt 追加 |
| --- | --- |
| 眼睛大一点 | `bigger sparkling anime eyes` |
| 脸圆一点 / 更 Q | `rounder chibi face, bigger head ratio` |
| 头发盘起来 | `hair tied up in a bun` |
| 换个画风：水彩 | `watercolor illustration style, soft washes` |
| 太写实了 | 提高画风权重、`--strength` 提到 0.72~0.78 |
| 表情不够夸张 | `exaggerated expression, stronger emotion` |
| 加了要求后不像本人了 | `--strength` 降到 0.5~0.58 |

---

## 4. 阶段 B：抠图与归一化（v1.3 四段式：抠前分析 → 定参 → 抠图 → 抠后比对）

v1.2 的教训：抠花了就临时调 `--tol`，越调越坏，白衣服被吃掉、眼镜片被挖空，还看不出来——因为没人看原图，也没人看抠完的样子。v1.3 把这一段拆成四步，**四个步骤全做完才算阶段 B 结束**，红线 5 管的就是这段。

### B1 抠前分析（必须先做，禁止张嘴就抠）

```bash
# 只分析不出图，逐张给出背景一致度 / 背景色 / 主体占比 / 推荐参数 / 风险
python {baseDir}/scripts/cutout.py --in raw/ --analyze
# 报告默认写 <out>/cutout.analyze.json；--out 可省，此时报告写到输入目录旁（raw/cutout.analyze.json）
```

同时**必须自己打开原图看一遍**（不是看小样拼图，是看原图），判定两件事：

1. **主体构成**：画面里哪些是"人"——脸、头发、脖子、衣服、手、眼镜、耳饰、发饰、项链。这些一个都不能少。
2. **哪些部件颜色接近背景**：这是误扣的唯一来源，常见四类——白/浅色衣服撞 white 或浅色底、黑发撞深色/黑底、眼镜片（半透、反光）撞浅底、浅色耳饰发饰撞浅底。

`--analyze` 输出的关键字段：

| 字段 | 含义 | 怎么用 |
| --- | --- | --- |
| **背景一致度** | 四角+上下边中点采样的颜色一致性 0~1 | ≥0.85 纯色可抠；0.55~0.85 勉强能键；<0.55 背景不是纯色，**回阶段 A 重生**，别在这里硬抠 |
| **背景色** | 采样出的 `#RRGGBB` | 与 `raw/manifest.json` 的 `bg.hex` 对不上时以 manifest 为准（生成时指定的才是真背景） |
| **主体占比估计** | 前景大约占画面多少 | 8%~85% 正常；<8% 人物太小或抠没了；>85% 人物顶满（小样就错了） |
| **主体内接近背景色像素** | 主体内部有多少像素与背景同色 | 这是"白衬衫被吃掉"的直接预警，越高越要看对照图 |
| **推荐参数** | `--tol` / `--bg-hex` 建议值 | 照抄，**禁止盲调** |
| **风险提示** | 逐条列出可能翻车的点 | 高风险（主体内同色 >15%）直接按"换背景色重生"处理 |

### B2 定参（按分析结果给，不许拍脑袋）

| 参数 | 怎么定 |
| --- | --- |
| `--chroma` | 纯色背景用 `auto`（读 manifest 的 `bg.hex`）；背景是渐变/场景用 `off`，交给 GrabCut |
| `--bg-hex` | 优先用 manifest 里的 `bg.hex`；`--analyze` 采样值只作交叉核对 |
| `--tol` | 用 `--analyze` 的推荐值（通常 28~36）；**不要凭手感在 18 附近乱试**，tol 越小越容易把主体留下但边缘毛，越大越容易连主体一起扣 |
| `--protect-radius` | 默认按短边 2.5% 自动，一般不用改；主体很小（占画面 <15%）时可手动调小 |
| `--no-protect` | **不要用**。关掉主体保护等于放弃回填，只在明确知道副作用（比如整张图就是纯背景素材）时才用 |

### B3 抠图（默认带主体保护）

```bash
# v1.3 标准写法：分析出的参数 + 主体保护 + 归一化 + 抠后校验 + 对照图，一条命令走完
python {baseDir}/scripts/cutout.py --in raw/ --out assets/ --normalize \
    --chroma auto --tol 32 --verify --compare
```

主体保护默认开启（v1.3 起不再是可选项）：色度键的结果会与 GrabCut 前景**交叉校验**，凡是 GrabCut 判为"确定前景"、却被色度键扣掉的区域（典型就是白衣服、脸、手、眼镜框），一律**回填**，只允许扣掉主体外圈的背景。这就是"不许把人物主体/衣服/配件当背景扣掉"的落地手段。

抠图链路本身仍是**五步递减**：① alpha 复用 → ② 色度键 → ③ GrabCut 引导 → ④ 四边 floodFill 兜底 → ⑤ 最大连通域 + 闭运算 + 填洞 + 羽化。**背景复杂度是在小样阶段决定的**，B1/B2 没做对，到这一步怎么调都是拆东墙补西墙。

### B4 抠后比对（必须看，看完才许进构建）

`--verify` 会逐张与**独立主体基准**比对，产出 `<out>/cutout.report.json`；`--compare` 会生成原图与抠图结果并排的对照图（默认 `<out>/compare/`，含 `compare.sheet.jpg`）。

**为什么不能用"自己的 mask 自证"**：v1.3.0 最初版把「GrabCut 的结果腐蚀一下当主体核心」再算保留率，于是只要抠图自己认定那是背景，保留率永远是 100%——`05_angry.png` 头发两侧被削、肩部衣领被抠掉，报告照样 PASS。现在改为先不看本次抠图结果，单独把主体估一遍：

```
独立主体基准（verify 内部独立跑，与 --chroma/--tol 无关）
  A = GrabCut 紧矩形初始化（内正区小）
  B = GrabCut 宽矩形初始化（边界带作确定背景）
  C = 四边泛洪反推（与画幅四边连通且颜色相近的算背景）
  agree = A ∩ B          → 保守主体（算 keep_ratio 与 IoU 用）
  core  = erode(agree, 5% 短边) → "必然属于主体"的核心区
  full  = A ∪ B ∪ C      → 主体上界（只用来在对照图上画参考轮廓）
```

九项指标与判定线（`report.json` 的 `verify_basis` / `thresholds` 会记录同一套口径）：

| 指标 | 含义 | PASS | WARN | FAIL |
| --- | --- | --- | --- | --- |
| `keep_ratio` | 主体保留率：独立基准核心区被保住的比例（**粗筛哨兵**，整块被吃才掉） | ≥ 95% | ≥ 90% | < 90% |
| `iou` | 与独立基准 `agree` 的 IoU（漏抠+多抠都扣分） | ≥ 0.85 | ≥ 0.75 | < 0.75 |
| `hole_rate` | 内部孔洞率：与外界不连通的被挖空面积占比 | ≤ 1.5% | ≤ 4% | > 4% |
| `edge_cut_ratio` | 贴边裁切：主体边界像素落在画幅四边（1.2% 短边内）的占比 | ≤ 0.8% | ≤ 3% | > 3% |
| `comp2_ratio` | 连通域断裂：第二大连通域 ÷ 最大连通域 | ≤ 0.05 | ≤ 0.25 | > 0.25 |
| `dent_ratio` | **轮廓削切**：左右边界相对包络的最大内向凹陷 ÷ 主体高度 | ≤ 0.48 | 0.48~0.50 | > 0.50 **且** 缺口面积 > 1% 主体（或 > 0.65 无条件） |
| `dent_area_ratio` | **缺口面积**：凹陷带累计缺失像素 ÷ 前景像素（辅助确认"削掉的是实心一块"） | ≤ 1% | > 1% | 与 `dent_ratio` > 0.50 同时成立即 FAIL |
| `fg_ratio` | 前景占比 | 8%~85% | 5%~95% | 越界 |
| `edge_color_diff` | 边缘色差：前景边缘与背景色的分离度 | ≥ 50 | ≥ 40 | < 40 |

> `dent_ratio` 是专门抓"头发两侧被削、肩部衣领被抠掉"这类**整块削进主体内部**的形态：正常轮廓每行只该缓慢变化，若某一行边界突然向内缩进一大截（超过主体高度的一半），几乎一定是从主体上啃掉了一块。`keep_ratio` 对这类局部削切不敏感（核心区可能一点没少），所以两项必须一起看。
>
> **`dent` 深凹直接判 FAIL（v1.3.0 收紧）**：实测 `05_angry.png` 右侧凹陷 0.54、缺口 2.39% 主体，坏图肉眼一眼可见，旧口径只给 WARN 而不拦构建，坏图会直接进游戏。现规则：`dent_ratio > 0.50` **且** `dent_area_ratio > 1%` → FAIL；`dent_ratio > 0.65` 无条件 FAIL；0.48~0.50 仍为 WARN 待目视。

**动作**：

1. 打开 `compare.sheet.jpg` **用眼睛看一遍**：红色是被独立基准判为主体、却被抠掉的像素（重点看红色是否成团落在头发两侧、肩线、衣领、手里道具上），黄线是独立基准的主体上界。脸还在吗？衣服完整吗？眼镜、耳饰、项链还在吗？头发边缘有没有紫边/白边？报告说 PASS 但眼睛看到人少了半个，按 FAIL 处理——报告只是辅助。
2. 有 FAIL：`cutout.py` 会以**退出码 2** 结束并在终端列出返工 key（同时写进 `report.json` 的 `summary.rework`）。处置方式是**回阶段 A 重生这几张**（换与主体色差更大的 `--bg` 重生纯色底 / 调提示词 / 重出表情），**不是在这里继续调 tol 硬抠**。
3. 有 WARN：看对照图决定，能接受就在小样阶段说明；不能接受同样回去重生。WARN 里只要出现 `孔洞`／`连通域断裂`／`贴边裁切` 任一条，默认按"主体被削"处理，回去换纯色底重生最省事。**深凹（`dent_ratio > 0.50` 且缺口 > 1%）不再走 WARN，已直接 FAIL**，会被构建门禁挡下。
4. 全 PASS 且目视无误，阶段 B 结束，才允许进阶段 C/D。

返工的标准动作（换一个与主体色差更大的背景色重生，再重抠）：

```bash
# 1) 重生不合格的几张，换成与主体色差更大的纯色底
python {baseDir}/scripts/gen_expressions.py --photo me.jpg --out raw/ --endpoint http://127.0.0.1:8790 \
    --features work/<主题名>/features.json --only 01_smug,04_taunt --bg green

# 2) 重新分析 + 重抠 + 重校验（对照图会一起刷新）
python {baseDir}/scripts/cutout.py --in raw/ --out assets/ --normalize --chroma auto --analyze
python {baseDir}/scripts/cutout.py --in raw/ --out assets/ --normalize --chroma auto --tol <新推荐值> --verify --compare
```

只想重出对照图（不重抠）时用 `--compare-only`，读 `--out` 目录里已抠好的同名图与原图比对。

**判定要可复现**：GrabCut 内部用 KMeans 初始化，随机源会让同一张图抠出不同结果（实测前景占比能在 27%~52% 之间跳）。所以：

- **同一批图一次跑完、别中途改文件顺序**，需要复跑就整批重跑，别只挑一张单独跑；
- 报告存疑时以 `--bg` 给纯色底（走色度键路线）最稳，色度键是确定性的；
- 判定异常时先看 `cutout.report.json` 里的 `metrics` 与 `baseline`，再决定返工还是复查。

**两件必做的事（不变）**：

1. **抠成透明 PNG**：AI 出的图带背景，游戏里是「从洞里钻出来」，必须透明。
2. **统一画布**：所有人物的头顶与脚底对齐到同一基准（默认 640×800，头顶留 6%）。**不做这一步，换表情时人物会上下乱跳**，是打地鼠游戏最刺眼的瑕疵。

出图时就把表情生成在**同一尺寸、同一构图**（如 832×1024，head and shoulders，centered）能大幅降低后续对齐难度。

`cutout.report.json` 是构建的硬前置：`build_game.py` 会检查 `assets/` 下有没有这份报告、里面有没有 FAIL，抠图没验或验出 FAIL 就构建，等于把阶段 B 白做。


---

## 5. 阶段 C：写 config.json

全量字段见 `references/config-schema.md`，可直接抄 `examples/config.qiaotan.json`（v1.4 原版 4 档配置）或 `examples/config.minimal.json`（3 档最小示例）改。

最常改的几处：

```jsonc
{
  "title": "敲谈姐儿",                    // 主题名：标题 / 页面 title / 产物文件名
  "version": "v1.4.0",
  "difficulties": {
    "easy": { "name": "轻松", "levels": 9, "lives": 15, "lifeCap": null, "target": 260, ... }
  },
  "groups": { "rise": [...], "hurt": [...], "mock": [...] },
  "rewards": {
    "goldEgg":  { "life": 1, "fallback": 50  },   // 金蛋：+1 命，命满折 50 分
    "colorEgg": { "life": 2, "fallback": 100 }    // 彩蛋：+2 命，命满折 100 分
  },
  "easterEgg": {
    "kicker": "All {levels} Levels Cleared",      // {levels} 自动替换为当前档关数
    "byDiff": {
      "hard": { "gift": "☕", "title": "敲 出 包 了 ！", "face": "07_dizzy",
                "prize": "prize.jpg", "text": "…<mark>请喝咖啡</mark>…" }
    }
  }
}
```

`easterEgg.byDiff` 里没写的难度会回落到 `byDiff.default`（若也没写，则复用第一个）。

`lifeCap: null` 表示该档加命无上限。

---

## 5.5 阶段 P：惊喜图（红线 3+4，先问后做）

惊喜图 = 通关后"领取惊喜"点开的那张图。**v1.0 是 skill 自己闷头生成的；v1.1 要求先问来源；v1.2 再加两件事**：除轻松外的每个难度都得有，且要先问用户"共用一张"还是"每档各一张"。

### 5.5.0 覆盖规则（先记住，别问错对象）

| 难度 | 有没有惊喜图 | 说明 |
| --- | --- | --- |
| 轻松 `easy` | **没有** | 通关只弹彩蛋页，"领取惊喜"按钮不出现；它是新手档，不给惊喜 |
| 普通 `normal` | **必须有** | 第一层惊喜 |
| 困难 `hard` | **必须有** | 第二层惊喜 |
| 地狱 `hell` | **必须有** | 最高档，通常给最好的那张 |

`build_game.py` 按这条规则校验：门禁里写了 `scope` 时会按用户选择逐档对账——`per_diff` 缺哪档就报错退出、`same` 则把三档统一指向 `--pick` 那张；同时把 `easy` 的 `prize` 强制清空并掐掉 `byDiff.default` 回落，避免轻松档误弹别档的图。**没写 `scope` 只会 WARN 不会拦**，所以门禁里必须带上它。

### 提问 1：来源（单选，三选一）

| 选项 | 后续动作 |
| --- | --- |
| **我上传** | 停下等图；拿到后用 `gen_prize.py --mode user --input <图片> --out work/<主题名>/prize` 入库（自动统一格式、可叠字）。分难度就每档各要一张，加 `--per-diff normal,hard,hell` |
| **系统自动生成** | 用**同一套表情人物**画全身卡通像，默认 3 个姿势（站立挥手 / 欢呼跳起 / 叉腰得意），出小样让用户挑一张 |
| **本地合成** | 不做 AI 生成，直接拿**用户照片或已定卡通像**套奖励样式（渐变底 + 彩屑 + 圆角卡/光环/勋章 + 文字），一次出 3 版式 × N 难度供用户挑；最快最稳、像素级可控 |

### 提问 2：覆盖范围（单选）

| 选项 | 后续动作 |
| --- | --- |
| **所有通关难度共用一张** | 定案为 `prize.jpg`；`gate.py` 写 `--scope same --pick ...` |
| **每个难度各不一样** | 按 normal / hard / hell 各定一张：`prize_normal.jpg` / `prize_hard.jpg` / `prize_hell.jpg`；`gate.py` 写 `--scope per_diff --prize-map ...` |

这两问答完再动手。用户说"随便你"，就默认 **本地合成 + 共用一张**，并在交付说明里写清"三档共用同一张惊喜图，要每档不同可以再改"。

### 提问 3：图上文字（单选）

| 选项 | 后续动作 |
| --- | --- |
| **我自己写** | 用户给什么就用什么（注意留空=不带字，也要明确问过） |
| **你帮我定** | 根据主题名 + 彩蛋文案拟 2~3 句候选（如「请喝咖啡」「今日份解压已发放」），让用户挑一句；**不要把候选直接当最终答案** |

### 路线 A：系统自动生成（img2img，全身卡通）

```bash
# 共用一张
python {baseDir}/scripts/gen_prize.py --mode ai \
    --init work/<主题名>/assets/normal.png --out work/<主题名>/prize \
    --poses 3 --endpoint http://127.0.0.1:8790 \
    --desc "cute young woman, short hair, glasses" --text "请喝咖啡"

# 每档各一张（一次性出 3 档 × 3 姿势 = 9 张，文字也可以按档分开）
python {baseDir}/scripts/gen_prize.py --mode ai \
    --init work/<主题名>/assets/normal.png --out work/<主题名>/prize \
    --per-diff normal,hard,hell --poses 3 --endpoint http://127.0.0.1:8790 \
    --text-map "normal:不错嘛;hard:厉害;hell:你是神吗"

# 没有本地引擎：导出 prompt 清单，交给 MCP / 线上模型
python {baseDir}/scripts/gen_prize.py --mode ai --per-diff normal,hard,hell --manifest-only --out work/<主题名>/prize
```

### 路线 B：本地合成（compose，纯 Pillow，最快最稳）

拿**用户照片**或**已定的卡通像**当主体，套上奖励样式，一次出多版式供挑：

```bash
# 3 档 × 3 版式 = 9 张候选，主题色 gold（另可选 rose / mint / night）
python {baseDir}/scripts/gen_prize.py --mode compose \
    --input work/<主题名>/assets/normal.png --out work/<主题名>/prize \
    --per-diff normal,hard,hell --theme gold \
    --layouts card,circle,badge --candidates 3 \
    --text-map "normal:不错嘛;hard:厉害;hell:你是神吗"

# 共用一张就省略 --per-diff
python {baseDir}/scripts/gen_prize.py --mode compose --input "D:/照片/me.jpg" \
    --out work/<主题名>/prize --theme gold --text "今日份解压已发放"
```

版式含义：`card` 圆角卡片（文字在下方）、`circle` 环形光晕（色环 + 主体居中）、`badge` 勋章款（顶部飘带 + 底部大字）。产物命名 `prize_<难度>_cand<n>_<版式>.png`，共用时无难度前缀。

### 路线 C：用户上传

```bash
# 共用一张
python {baseDir}/scripts/gen_prize.py --mode user --input "D:/照片/gift.jpg" \
    --out work/<主题名>/prize --text "生日快乐"

# 分难度：每档各跑一次，用 --diff 标明归属
python {baseDir}/scripts/gen_prize.py --mode user --input "D:/照片/g1.jpg" --diff normal --out work/<主题名>/prize --text "不错嘛"
python {baseDir}/scripts/gen_prize.py --mode user --input "D:/照片/g2.jpg" --diff hard   --out work/<主题名>/prize --text "厉害"
python {baseDir}/scripts/gen_prize.py --mode user --input "D:/照片/g3.jpg" --diff hell   --out work/<主题名>/prize --text "你是神吗"
```

### 统一收尾：拼小样 → 用户挑 → 定案

```bash
# 1. 拼小样（候选可能很多，cols 按张数调）
python {baseDir}/scripts/make_sheet.py --in work/<主题名>/prize \
    --out work/<主题名>/prize/sheet_prize.jpg --cols 3 --title "惊喜图候选，用哪张？"
```

发给用户 → **停下来等明确选择** → 再定案（`--pick` 会把选中图统一尺寸、叠上文字，并按归属写成 `prize.jpg` 或 `prize_<难度>.jpg`）：

```bash
# 共用
python {baseDir}/scripts/gen_prize.py --pick work/<主题名>/prize/prize_cand1_card.png \
    --out work/<主题名>/prize --text "请喝咖啡"

# 分难度：每档挑一次，用 --diff 标明
python {baseDir}/scripts/gen_prize.py --pick work/<主题名>/prize/prize_normal_cand2_circle.png --diff normal --out work/<主题名>/prize --text "不错嘛"
python {baseDir}/scripts/gen_prize.py --pick work/<主题名>/prize/prize_hard_cand1_badge.png   --diff hard   --out work/<主题名>/prize --text "厉害"
python {baseDir}/scripts/gen_prize.py --pick work/<主题名>/prize/prize_hell_cand3_card.png    --diff hell   --out work/<主题名>/prize --text "你是神吗"
```

### 两个要点（系统生成路线）

- **姿势一致性靠 init**：起始图用 `assets/normal.png`（已经抠图+统一画布的那张），`--strength 0.80`（半身扩全身，低了只改脸不改构图，高了不像本人）。
- **全身构图靠 prompt**：`full body shot from head to toe` 必须留在正向词里，负向词已预置 `cropped feet / half body only / close-up portrait`。出图后检查脚有没有被裁，裁了加 `--height 1344` 重跑。

### 落进 config（按覆盖范围二选一）

定案图复制进 `assets/` 后，`easterEgg.byDiff` 有两种写法：

```jsonc
// 共用一张：三档都指同一个文件（easy 不写 prize）
"byDiff": {
  "normal": { "prize": "prize.jpg", ... },
  "hard":   { "prize": "prize.jpg", ... },
  "hell":   { "prize": "prize.jpg", ... }
}

// 每档不同：各指各的
"byDiff": {
  "normal": { "prize": "prize_normal.jpg", ... },
  "hard":   { "prize": "prize_hard.jpg",   ... },
  "hell":   { "prize": "prize_hell.jpg",   ... }
}
```

**别给 `easy` 写 `prize`**，也别只写一个 `byDiff.default` 指望自动铺满——v1.2 的 `build_game.py` 会显式掐掉 easy 的回落，并逐个校验 normal/hard/hell 的图是否存在。

写门禁（`--scope` 必填，没有默认值，等于必须问过用户）：

```bash
# 共用一张
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json \
    --prize ai_generated --scope same --poses 3 \
    --pick work/<主题名>/prize/prize.jpg \
    --text "请喝咖啡" --text-source user --quote "三档都用这一张，文字就写请喝咖啡"

# 每档各一张
python {baseDir}/scripts/gate.py --file work/<主题名>/gate.json \
    --prize ai_generated --scope per_diff \
    --prize-map "normal:work/<主题名>/prize/prize_normal.jpg;hard:work/<主题名>/prize/prize_hard.jpg;hell:work/<主题名>/prize/prize_hell.jpg" \
    --text-source user --quote "每个难度用不同的图，普通那张写不错嘛"
```

`--scope per_diff` 时，`--prize-map` 里必须**覆盖全部通关难度（normal / hard / hell）**且每张图真实存在，缺一个 `gate.py` 就拒绝写入；`--scope same` 则必须给 `--pick` 且文件存在。

---

## 6. 阶段 D：构建

```bash
python {baseDir}/scripts/build_game.py \
    --config work/<主题名>/config.json \
    --assets work/<主题名>/assets/ \
    --out work/<主题名>/dist/ \
    --gate work/<主题名>/gate.json \
    --single
```

**构建前会校验 `gate.json` 的四道门禁**：照片来源 / 表情小样（含背景纯色检查）/ 惊喜图来源与覆盖范围 / **身份一致性（特征 JSON + 对照图 + 相似度评分）**，没确认齐直接报错退出并列出缺口；惊喜图还会按 `scope` 逐个难度对账（`per_diff` 缺哪档报哪档，`same` 则三档共用一张）。身份门禁里相似度 <65 分同样拒绝构建。这是 v1.1 起立的硬约束，v1.2 把"每档都要有惊喜图"纳进校验，v1.3 把"像不像"也变成了门禁。

**构建前还会校验 `assets/cutout.report.json`**：报告不存在（没跑 `--verify`）或里面出现 FAIL，`build_game.py` 直接拒绝构建——抠图没验就构建，等于把阶段 B 白做。要重跑就回阶段 B 补 `--verify --compare`。

不要用 `--allow-no-gate` 绕过（该参数仅供调试模板，一旦用上就等于把四道门禁全绕过、六条红线形同虚设）。

产出：

- `dist/index.html` —— 目录版，图片走 `assets/` 外链，便于后续改素材
- `dist/<主题名>_单文件版_<版本>.html` —— 单文件版，**全部图片内嵌 data URI，零外部依赖，可直接发微信/邮件**

脚本会自检并打印：静态外部引用数（目录版可为素材引用，单文件版必须为 0）、表情数量、各档关数、文件字节与 SHA256。**单文件版静态外部引用不为 0 就是构建失败**，不要去手工修补。

---

## 7. 阶段 E：回归校验（交付前必跑）

```bash
python {baseDir}/scripts/verify_game.py \
    --dir dist/ --config config.json --out verify.json --port 9433
```

校验覆盖：

- 页面无 JS 异常、无 console error
- 标题 / 眉标 / 引导语 / 版本号与 config 一致
- 难度卡片数量、每档「N 关 / N 条命 / 上限」文案正确
- 切难度后 `#maxLvl` 数值正确
- 开局后 `state === 'playing'`、HUD 显示、菜单隐藏
- 全部表情 `naturalWidth > 0`（防破图）
- 彩蛋页：标题 / 礼物 emoji / 文案 / 头像 / `{levels}` 标语正确，纸屑 canvas 已实际绘制（抽样 alpha>8 像素 > 200）
- 「领取惊喜」：奖励图加载成功、返回按钮 3 秒后出现、惊喜页纸屑已绘制、返回主菜单正常
- 单文件版：无任何外部 `src`/`href`

`errs` 必须为 `[]` 才算通过。脚本用 CDP 连接本机 Edge，若端口占用换 `--port`。

---

## 8. 阶段 F：交付

交付物清单（用 `yyb-product` 卡片声明，每个路径只出现一次）：

1. `<主题名>_单文件版_<版本>.html` —— 主交付物，双击即玩，可直接发人
2. `index.html` + `assets/` —— 目录版，方便二次修改
3. `config.json` —— 需求快照，下次改需求只改它
4. `verify.json` —— 校验报告
5. （可选）GitHub Release：仓库 + tag + 附件，发布流程见 `references/pitfalls.md` §发布
6. **技能包本身**（要分发给别人用时）：`photo-mole-game_v<版本>.zip` + `manifest.json`，对方解压后跑 `install.ps1` 即装进自己的 WorkBuddy，详见 `INSTALL.md`

第 6 项只在"把这套流水线交给别人用"时才需要出；只交一个游戏的话，前 1~4 项就够。

交付时告诉用户三件事：游戏怎么开（双击单文件）、怎么改（改 config 重跑 build）、手机上能不能玩（单文件版可直接用手机浏览器打开）。

---

## 9. 复用与二次迭代

| 用户后续要求 | 做法 |
| --- | --- |
| 改标题 / 文案 / 关数 / 奖励 | 只改 `config.json`，重跑 build + verify，秒级完成 |
| 换一张照片重做形象 | 阶段 A → B → 把 `assets/` 换掉 → build |
| 只改某几个表情 | `gen_expressions.py --only key1,key2 --extra-prompt "..."` → cutout → build |
| 换通关惊喜图 | `gen_prize.py --mode user/ai/compose` 重出 → 放进 `assets/` → 改 `easterEgg.byDiff.*.prize` 文件名 → build（改了来源或覆盖范围要重写 gate 的 prize 项，含 `--scope`） |
| 惊喜图从"共用一张"改成"每档不同"（或反过来） | 重跑 `gen_prize.py --per-diff normal,hard,hell` 出图 → 改 `byDiff` 三个难度的 `prize` → `gate.py --prize --scope per_diff --prize-map ...` 重写 → build |
| 小样背景要换色重抠 | `gen_expressions.py --only <keys> --bg green` 重生 → `make_sheet.py`（看 bgcheck）→ `cutout.py --chroma auto` → build |
| 只改惊喜图上的字 | `gen_prize.py --pick 原图 --out prize --text "新文字"` → 覆盖 `assets/prize.jpg` → build |
| 加难度档 | `difficulties` 加一项 + 加入 `diffOrder` + 在 `easterEgg.byDiff` 补配置 |
| 加/减表情 | 同步 `expressions`、`groups`、`deco` 三处，缺一处就会渲染空白 |

---

## 10. 已知坑（务必先读）

完整版见 `references/pitfalls.md`，最容易踩的这几处：

1. **单文件版只替换了第一处头像** → 彩蛋页破图。必须全量替换所有图片引用为 data URI。
2. **Playwright 直接 launch 会卡 180 秒** → 必须用 CDP 连接本机 Edge（`--headless=new --remote-debugging-port`）。
3. **校验脚本在 600 秒主会话里会超时** → 长任务用 subprocess 起独立进程，结果先 `json.dump` + `flush` + `fsync`，末尾 `os._exit(0)`。
4. **表情不做统一画布** → 游戏里人物换表情时上下乱跳，看似"抖动 bug"实为素材尺寸不一致。
5. **用 `--allow-no-gate` 绕过门禁** → 等于把六条红线全废掉，产出的游戏必然少了"用户确认"和"抠图校验"这两环，就是 v1.0 翻车的复现。
6. **小样背景不纯**（渐变/场景/投影） → 抠图必花边：白衬衫被当背景吃掉、头边一圈紫边。v1.2 的做法是在出图阶段就用 `--bg magenta`（或 green/blue/white），并用 `make_sheet.py` 的 bgcheck 卡住 FAIL，**不要在 cutout 阶段靠调 `--tol` 补救**。
7. **惊喜图只配了 `byDiff.default`** → 轻松难度通关也弹同一张，"打得越狠惊喜越好"的层次没了。v1.2 要求 normal/hard/hell 各档显式配置，`easy` 不配。
8. **不看原图直接抠**（v1.3 新增） → `--tol` 拍脑袋给 18，白衣服/眼镜/耳饰被当背景扣掉，报告还显示 PASS（因为报告也只看它自己那一套指标）。**先 `--analyze` 定参，再抠，抠完必须看对照图**，这是红线 5。
9. **抠完不看报告就构建**（v1.3 新增） → `assets/cutout.report.json` 缺失或含 FAIL 时 `build_game.py` 会直接拒绝构建；靠 `--allow-no-gate` 硬过等于把风险留给用户第一眼。
10. **只写 `--desc` 不写特征**（v1.3 新增） → 出的是"通用动漫脸"，用户一句"这不像我"就得整套重做。走 §2.5 阶段 A0：特征 JSON → `--features` → 出图 → `identity.py --compare-sheet` 评分 ≥80 再给用户看。
11. **相似度评分自评**（v1.3 新增） → 不许"我觉得挺像"。`gate.py --identity-score` 必须来自 `identity.py --compare-sheet` 的实际输出，且要带 `--identity-compare` 对照图与用户原话。
12. **校验自己判自己**（v1.3 新增） → 拿本次抠出的 mask 当主体基准去算保留率，头发两侧被削、肩部衣领被抠掉也能报"保留 100% → PASS"（`05_angry.png` 的漏判就是这么来的）。校验必须先建**独立主体基准**（两套 GrabCut 初始化取交 + 四边泛洪反推取上界），再加 `dent_ratio` 抓局部削切；报告 PASS 也要看对照图，眼睛与报告冲突时以眼睛为准。

---

## 11. 文件结构

```
photo-mole-game/
├── SKILL.md                     # 本文件（v1.3.0）
├── README.md                    # 面向人的简介与安装方法
├── INSTALL.md                   # 部署到 WorkBuddy 的三种方式
├── manifest.json                # 技能包元信息（版本、文件清单、校验和）
├── install.ps1                  # Windows 一键安装脚本
├── assets/
│   └── game_template.html       # 游戏模板（含 __MOLE_CONFIG__ 占位符，勿手改逻辑）
├── scripts/
│   ├── gate.py                  # 四道门禁（照片/表情/惊喜图/身份相似度）+ 惊喜图覆盖校验
│   ├── identity.py              # 真人面部特征 JSON（--template/--validate/--emit）+ 原图卡通对照评分
│   ├── gen_expressions.py       # 表情批量出图（纯色背景 + --features 身份锁定）/ prompt 清单导出
│   ├── make_sheet.py            # 小样拼图 + 背景检查 bgcheck（v1.2）
│   ├── cutout.py                # 抠图：--analyze 定参 / 默认主体保护 / --verify 报告 / --compare 对照图 + 统一画布
│   ├── gen_prize.py             # 惊喜图：上传入库 / 全身多姿势生成 / 本地合成多版式 / 叠字
│   ├── build_game.py            # 构建目录版 + 单文件版（校验 gate.json 四道门禁 + cutout.report.json）
│   └── verify_game.py           # 无头回归校验
├── examples/
│   ├── config.qiaotan.json      # v1.4 原版 4 档配置（繁）
│   └── config.minimal.json      # 3 档最小示例（简）
└── references/
    ├── config-schema.md         # config 全字段说明
    ├── expressions.md           # 11 表情清单 + 提示词配方 + 身份锁定词
    └── pitfalls.md              # 踩坑与发布流程
```

运行时产物（都在 `work/<主题名>/` 下，不进技能包）：`raw/`（原图 + manifest.json + sheet.bgcheck.json）、`assets/`（透明 PNG + `cutout.report.json` + `compare/`）、`features.json`（真人特征）、`identity.compare.jpg` + `identity.score.json`（对照与评分）、`gate.json`、`config.json`、`dist/`。

环境依赖：Python 3.11、Pillow、numpy、opencv（`pip install pillow numpy opencv-python`）、Playwright（校验用）、本机 Edge。

## 12. 变更记录

### v1.3.0（2026-11-19）

按实际交付反馈加固两处最容易"交付后才被发现"的硬伤：抠图吞主体、卡通不像本人。两条都升成红线并落到脚本级校验。

1. **抠图加固（红线 5）**：`cutout.py` 新增 `--analyze`（只分析不出图，给背景采样一致度、背景色、主体占比、推荐 `--tol`/`--bg-hex` 与风险提示）、**默认开启主体保护**（色度键结果与 GrabCut 前景交叉校验，落在主体内部的被扣区域回填，人物主体/衣服/配件/头发/眼镜/饰品不再被当背景删）、`--verify`（抠后与原图逐张比对主体保留率、内部孔洞率、前景占比、边缘色差，产出 `cutout.report.json`，FAIL 非零退出并列返工 key）、`--compare`（原图/抠图并排对照图 + 拼版总览）。SKILL.md 阶段 B 重写为「抠前分析 → 定参 → 抠图 → 抠后比对」四段，明确禁止盲调参数、抠后必须看报告与对照图，FAIL 一律返工重生。
2. **卡通一致性加固（红线 6）**：新增 `scripts/identity.py`（`--template` 产真人面部特征 JSON 骨架，覆盖脸型/肤色/发型分缝刘海/眉/眼与眼皮瞳色睫毛/眼镜/鼻/嘴/耳/特殊标记/耳饰等配件/服装/年龄感；`--validate` 校验必填；`--emit` 出英文 desc 与身份锁定词；`--compare-sheet` 出原图卡通对照并打分）。`gen_expressions.py` 新增 `--features`，把特征写进 desc 与正向锁定词，负向词补「不同的人 / 通用动漫脸 / 发型不符 / 缺眼镜 / 脸型改变」。`gate.py` 新增身份一致性门禁（评分 + 对照图 + 用户原话留痕，<65 拒写），`build_game.py` 缺该门禁或评分 <65 直接拒绝构建。SKILL.md 新增 §2.5 阶段 A0「真人面部特征分析」：先图像理解逐字段分析照片 → 特征 JSON + 中文特征总结给用户确认 → 出图后对照评分。
3. **门禁与文档**：红线表四条扩六条；`build_game.py` 新增 `cutout.report.json` 校验（缺失或有 FAIL 拒绝构建）；流水线总览、脚本职责表、已知坑（新增 8~11 条）、文件结构同步更新；`README.md` / `INSTALL.md` / `references/*` / `manifest.json` 升版。
4. **抠后校验的判定口径重做（v1.3.0 内修正）**：首版 `--verify` 用"把本次 mask 腐蚀当主体核心区再算保留率"，属于自己判自己——`05_angry.png` 头发两侧被削、肩部衣领被抠掉，报告仍是"保留 100% / 孔洞 0% → PASS"。改为**独立主体基准**：`GrabCut 紧矩形初始化 ∩ GrabCut 宽矩形初始化` 得保守主体 `agree`（与 `--chroma`/`--tol` 无关），`core = erode(agree, 5% 短边)` 算 `keep_ratio`，`agree` 算 `iou`，`四边泛洪反推` 并入 `full` 只作主体上界；指标扩为八项并新增 `dent_ratio`（逐行左右边界相对滑动窗包络的最大内向凹陷 ÷ 主体高度，专拦"啃掉一块头发/衣领"）、`edge_cut_ratio`（贴画幅四边被切）、`comp2_ratio`（第二大连通域断裂）。定级：`keep_ratio < 0.90` 或 `iou < 0.75` 或 `fg_ratio` 越界 → FAIL（退出码 2 + 返工 key）；`keep_ratio < 0.95`、孔洞 1.5%~4%、连通域断裂、贴边裁切、边缘色差 <50、`dent_ratio` >0.48 → WARN 并写清具体原因。`--compare` 的涂红参照同步换成独立基准（红=基准判为主体却被抠掉）。

5. **深凹改判 FAIL，坏图不再进游戏（v1.3.0 内再修正）**：`05_angry.png` 右侧凹陷 0.54、缺口 2.39% 主体（头发两侧+肩部衣领被削），旧口径只判 WARN，而 WARN 不阻塞构建，坏图直接进游戏。现改为：`dent_ratio > 0.50` **且** `dent_area_ratio > 1%` → **FAIL**（新增第九项指标 `dent_area_ratio`：凹陷带累计缺失像素 ÷ 前景像素，确认削掉的是实心一块）；`dent_ratio > 0.65` 无条件 FAIL；0.48~0.50 仍 WARN。复跑实测：`05_angry` 判 FAIL（退出码 2，`summary.rework=["05_angry"]`），`01_smug` 仍 PASS。`keep_ratio < 0.95`、孔洞 1.5%~4%、连通域断裂、贴边裁切、边缘色差 <50 维持 WARN。

### v1.2.0（2026-11-18）

按实际使用反馈加固三处，全部落到脚本级校验，不靠"记得这么做"：

1. **小样背景一律纯色（为抠图让路）**：`gen_expressions.py` 新增 `--bg magenta|green|blue|white`（默认 magenta）与 `--bg-hex`，提示词强约束 `completely uniform fill, no gradient, no vignette, no shadow, no props`，负向词加入渐变/场景/投影/道具；背景色值写入 `raw/manifest.json` 的 `bg.hex`。`cutout.py` 改为五步递减，色度键优先读 manifest 色值（`--chroma auto`），不再一上来硬抠。`make_sheet.py` 默认 `--check-bg`，逐张判 PASS/WARN/FAIL 并输出 `sheet.bgcheck.json`，拼图右上角印背景色块；`gate.py` 见到 FAIL 直接拒绝写入表情确认。
2. **惊喜图覆盖每个非轻松难度**：`easy` 不配惊喜图（通关仅弹彩蛋页），`normal / hard / hell` 每档必须有定案图。`build_game.py` 强制校验并显式掐掉 easy 的 `byDiff.default` 回落；模板侧 `eggHasPrize()` / `showPrize()` 改为"该难度没配图就不给入口、不弹窗"，绝不拿表情图冒充惊喜图。
3. **惊喜图先问来源与覆盖范围，再合成供挑**：来源三选一（我上传 / 系统自动生成 / **本地合成**），覆盖范围二选一（共用一张 / 每档各一张）。`gen_prize.py` 新增 `--mode compose`（纯 Pillow 合成，3 版式 card/circle/badge × 4 主题色 gold/rose/mint/night，可 `--per-diff` 批量出 9 张候选）与 `--per-diff` / `--text-map` / `--diff` 参数；`gate.py --prize` 新增 `--scope same|per_diff`（无默认值，必须问过用户）与 `--prize-map`，`per_diff` 缺档直接拒绝。

### v1.1.0（2026-11-18）

按实测反馈修三处流程漏洞，并把"口头要求"升级为"脚本级硬门禁"：

1. **照片来源不再被抢答**：新增 §1.1 三选一（我上传 / 我给路径 / 你帮我找），选前两项必须停下等交付，禁止把"用户还没发图"当成"用户没提供"去自动检索。
2. **表情小样确认回归**：`make_sheet.py` 出拼图 → 发给用户 → 三选一 → `gate.py` 留痕，缺痕不许进抠图/构建。
3. **惊喜图流程补齐**：先问来源（上传 / 系统生成），再问文字（用户给 / agent 拟候选）；系统生成改为**全身卡通多姿势**（`gen_prize.py`），出小样让用户挑定。
4. **构建强制门禁**：`build_game.py` 校验 `gate.json`，三项未确认直接拒绝构建。
5. **分发与自动部署**：补 `manifest.json` / `INSTALL.md` / `install.ps1`，解压即用、可被 WorkBuddy 一键挂载。

*（内容由AI生成，仅供参考）*
