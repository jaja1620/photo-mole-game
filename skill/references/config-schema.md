---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_d3ec86a8e22511f1b140525400de85a5
    ReservedCode1: rDkpCecMMAE8rYSJ5s8qpIjl/xZKLRV6rQlKysoQTYQqTwrehoptxgDwkM/uMgY3umkIMQ2ORDc1FDR0Tmg5cqOyDLql0epWHBAqcefGL5GkvaPUZBwjaNy3lfdNJz5616bhOxjYRRqM5OqoorX/Ht4UzIXVKoIPxKgBdm0Wo9C1RQ8Klf85DQ+pFsI=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_d3ec86a8e22511f1b140525400de85a5
    ReservedCode2: rDkpCecMMAE8rYSJ5s8qpIjl/xZKLRV6rQlKysoQTYQqTwrehoptxgDwkM/uMgY3umkIMQ2ORDc1FDR0Tmg5cqOyDLql0epWHBAqcefGL5GkvaPUZBwjaNy3lfdNJz5616bhOxjYRRqM5OqoorX/Ht4UzIXVKoIPxKgBdm0Wo9C1RQ8Klf85DQ+pFsI=
---

# config.json 全字段说明

`build_game.py --config` 吃的是这一份 JSON。除 `title` 外几乎全部有默认值，**改需求 = 改这份文件 + 重跑 build**，不要动模板。

示例见 `examples/config.qiaotan.json`（v1.4 原版，4 档繁配）与 `examples/config.minimal.json`（3 档最小示例）。

---

## 1. 基本信息

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 必填 | 主题名。用于 `<title>`、菜单大标题、产物文件名（`<title>_单文件版_<version>.html`） |
| `subtitle` | string | `""` | 副标题，页面 title 显示为 `title · subtitle` |
| `kicker` | string | `""` | 菜单顶部眉标，CSS 会转大写显示（写 `Office Arcade · No.01` 即可） |
| `lead` | string | `""` | 菜单引导语，一句话 |
| `version` | string | `v1.0.0` | 版本号，显示在 `.m-ver`，也进产物文件名 |
| `subject` | object | `{}` | `{ "name": "她", "pronoun": "她" }`，用于玩法说明等动态文案里的人称 |
| `assetDir` | string | `assets/` | 目录版图片相对路径前缀 |
| `defaultDiff` | string | `diffOrder[0]` | 默认选中难度 |
| `diffOrder` | string[] | `["easy","normal","hard","hell"]` | 难度顺序，**决定菜单卡片顺序** |

---

## 2. 难度 `difficulties`

键名可自定义（`easy` / `normal` / `hard` / `hell` 是约定俗成，想用 `novice` / `boss` 也行），但**必须与 `diffOrder` 一致**。

| 子字段 | 说明 |
| --- | --- |
| `name` | 显示名（轻松 / 普通 / 困难 / 地狱） |
| `desc` | 卡片副文案（"慢慢冒头"） |
| `levels` | **关数**。这是用户说「做 9 关」时要改的字段 |
| `interval` | 冒头间隔（ms），越小越密 |
| `up` | 停留时长（ms），越小越难 |
| `target` | 每关目标分 |
| `lives` | 初始命数 |
| `lifeCap` | 加命累计上限；`null` = 无上限（对应卡片文案「无上限」） |
| `maxSame` | 同时出现的洞数上限 |

判定逻辑：`levelMax()` 取 `DIFF[当前难度].levels`，兜底常量 `LEVEL_MAX_ALL`（15）。**加难度档时务必同时补 `levels`**，否则该档会退化成 15 关。

默认四档（v1.4 实测定型，可直接抄）：

| 档 | 关数 | 命 | 上限 | interval | up | target | maxSame |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 轻松 | 9 | 15 | 无上限 | 1050 | 1550 | 260 | 1 |
| 普通 | 9 | 10 | 20 | 810 | 1150 | 450 | 2 |
| 困难 | 12 | 8 | 12 | 600 | 900 | 700 | 3 |
| 地狱 | 15 | 6 | 10 | 420 | 700 | 1000 | 4 |

---

## 3. 表情 `expressions` / `groups` / `deco`

```jsonc
"expressions": { "normal": "normal.png", "05_angry": "05_angry.png" },   // key -> assets 下文件名
"groups": {
  "rise": ["normal", "01_smug", "02_tongue"],   // 从洞里冒出来（≥2）
  "hurt": ["05_angry", "06_cry"],               // 被砸中（≥2）
  "mock": ["04_taunt", "09_disdain"]            // 嘲讽/逃跑（≥1）
},
"deco": ["01_smug", "02_tongue"]                // 菜单周围装饰头像（可选，默认全部）
```

约束：

- `normal` 必须存在——它同时充当菜单装饰兜底与结果页头像
- `groups` 里引用的 key 必须在 `expressions` 里存在，否则运行时图片为空
- `deco` 为空数组时自动回落到全部表情
- 增删表情要**三处同步**（expressions / groups / deco），缺一处就是空白图

---

## 4. 奖励 `rewards`

```jsonc
"rewards": {
  "goldEgg":  { "life": 1, "fallback": 50,  "text": "金蛋！" },
  "colorEgg": { "life": 2, "fallback": 100, "text": "彩蛋！" }
}
```

- `life`：砸中加几条命
- `fallback`：命已满时改为加分
- 加命不能超过当前难度 `lifeCap`（`null` 时不限）

---

## 5. 彩蛋页 `easterEgg`

打通当前难度全部关卡后进入。

```jsonc
"easterEgg": {
  "kicker": "All {levels} Levels Cleared",   // {levels} 自动替换为当前档关数
  "tip": "点「领取惊喜」看专属彩蛋图",         // 拼接在玩法说明的「彩蛋」一行
  "byDiff": {
    "easy": { "gift": "🍦", "title": "打 服 了 ！", "face": "01_smug",
              "prize": "prize_normal.jpg",
              "text": "…<mark>请你吃冰棍儿</mark>～<br>凭通关截图领取" }
  }
}
```

| 子字段 | 说明 |
| --- | --- |
| `gift` | 彩蛋页顶部的礼物 emoji |
| `title` | 大标题，字间可加空格做出"加粗标题感" |
| `face` | 彩蛋页头像用的表情 key |
| `prize` | **通关奖励图文件名**（放 `assets/` 下）。用户自行上传的图就填这里 |
| `text` | 正文，支持 `<mark>` 高亮与 `<br>` 换行 |

取值优先级：`byDiff[当前难度]` → `byDiff.default` → `byDiff` 的第一项。

「领取惊喜」按钮点击后：全屏展示 `prize` 图 → 纸屑下落 → 3 秒后出现「返回主菜单」。这个 3 秒是硬编码 3000ms，改它要动模板。

---

## 6. 评分档位 `ranks`（可选）

```jsonc
"ranks": {
  "S": { "label": "完美判决", "say": "……" },
  "A": { "label": "从容过关" }
}
```

键为 `S/A/B/C/F`，默认值：
`S=完美判决`（命中率 ≥0.9）、`A=从容过关`（≥0.75）、`B=险险通过`（≥0.6）、`C=勉强及格`、`F=本局结束`。
只写你想覆盖的键即可，其余保持默认。

---

## 7. 玩法说明 `tips` / `tipsExtra`（可选）

```jsonc
"tipsExtra": { "expr": "自定义的「表情」那一行说明" },
"tips": ["整段替换的多行玩法说明（数组每项一行）"]
```

- 不写 `tips` 时按难度与表情自动生成默认说明
- 不写 `tipsExtra.expr` 时用默认的表情说明文案

---

## 8. 最小可用 config

只有这些是必须的（其余全部有默认）：

```jsonc
{
  "title": "敲小人",
  "version": "v1.0.0",
  "diffOrder": ["easy", "normal", "hard"],
  "difficulties": {
    "easy":   { "name": "新手", "levels": 3, "interval": 1200, "up": 1700, "target": 60,  "lives": 12, "lifeCap": null, "maxSame": 1 },
    "normal": { "name": "进阶", "levels": 6, "interval": 900,  "up": 1300, "target": 150, "lives": 9,  "lifeCap": 15,   "maxSame": 2 },
    "hard":   { "name": "挑战", "levels": 9, "interval": 550,  "up": 850,  "target": 300, "lives": 7,  "lifeCap": 9,    "maxSame": 3 }
  },
  "expressions": { "normal": "normal.png", "01_smug": "01_smug.png" },
  "groups": { "rise": ["normal", "01_smug"], "hurt": ["normal"], "mock": ["01_smug"] }
}
```

（真实使用建议至少 6 张表情，此处的 2 张仅为说明"最小可跑"的边界。）
*（内容由AI生成，仅供参考）*
