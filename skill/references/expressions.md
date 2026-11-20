---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_d4e226d9e22511f1a768525400cd780f
    ReservedCode1: fyAstyylcV/pk2nqAN3VUKymdVIdTd8NhFtJCTL/iyrIcd+xg3xm4EBQ0892w6pghmNEohAJwQbWP50ZUfND68sPK5/xlGGk96kmsd6Mj55pyB6kYHSwkfZ/TzUHYiiSLcp+cGsGQGLw2jTKZ77wsVmWC4M5/z5JwAhTHy02vHlG1xLhXZSJ8jDi3RE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_d4e226d9e22511f1a768525400cd780f
    ReservedCode2: fyAstyylcV/pk2nqAN3VUKymdVIdTd8NhFtJCTL/iyrIcd+xg3xm4EBQ0892w6pghmNEohAJwQbWP50ZUfND68sPK5/xlGGk96kmsd6Mj55pyB6kYHSwkfZ/TzUHYiiSLcp+cGsGQGLw2jTKZ77wsVmWC4M5/z5JwAhTHy02vHlG1xLhXZSJ8jDi3RE=
---

# 表情清单与提示词配方

## 1. 标准 11 表情

`scripts/gen_expressions.py` 内置下表，key 即 `assets/` 下的文件名主干（`.png`）。

| # | key | 中文名 | 英文表情描述（进 prompt） | 归属组 |
| --- | --- | --- | --- | --- |
| 0 | `normal` | 标准微笑 | `gentle neutral smile, calm eyes` | rise |
| 1 | `01_smug` | 得意坏笑 | `smug confident smirk, one eyebrow raised` | rise |
| 2 | `02_tongue` | 吐舌眨眼 | `playful tongue sticking out, winking` | rise / mock |
| 3 | `03_tease` | 挑衅坏笑 | `teasing grin, squinting eyes, cheeky look` | rise |
| 4 | `04_taunt` | 嚣张挑逗 | `cocky taunt expression, chin up, half-lidded eyes` | rise / mock |
| 5 | `05_angry` | 生气嘟嘴 | `angry pouting face, eyebrows furrowed, cheeks puffed` | hurt |
| 6 | `06_cry` | 哇哇大哭 | `crying face, big teardrops, trembling mouth` | hurt |
| 7 | `07_dizzy` | 被打懵/晕 | `dizzy stunned face, spiral eyes, mouth open in a daze` | hurt |
| 8 | `08_surprised` | 吃惊 | `surprised face, wide eyes, mouth open in shock` | （备用/可入 rise） |
| 9 | `09_disdain` | 鄙视白眼 | `disdainful side-eye, cold contemptuous look` | rise / mock |
| 10 | `10_sad` | 委屈难过 | `sad dejected face, drooping eyes, frown` | hurt |

> `08_surprised` 在 v1.4 里存在但未进三组，属于"备而不用"。要么把它加进 `rise`，要么从 `expressions` 里删掉，避免做无用功。

---

## 2. 提示词模板

**正向**（`gen_expressions.py` 内 `PROMPT_POS`，v1.2 起内置纯色底、v1.3 起尾部追加身份锁定词）：

```
chibi anime cartoon portrait of {desc}, {expr}, upper body head and shoulders,
facing viewer, centered, {style}, thick clean outline, soft cel shading,
{bg} background ({bg_hex}), completely uniform fill, no gradient, no vignette,
no shadow, no props, high quality, sharp focus
```

- `{desc}` = `--desc`；**带 `--features features.json` 时由特征 JSON 自动拼英文描述**，权重优先于 `--desc`
- `{expr}` = 上表的表情描述
- `{style}` = `--style`，默认 `kawaii flat illustration style, 2d anime, vivid but soft colors`
- `{bg}` / `{bg_hex}` = `--bg magenta|green|blue|white`（默认 magenta）或 `--bg-hex #RRGGBB`，纯色是抠图前提，**不要删**
- 传了 `--features` 时 prompt 末尾追加身份锁定片段（同发型、同眼镜、同脸型、可辨认是本人），由 `identity.py --emit` 生成

**负向**（`PROMPT_NEG` + v1.3 的 `IDENTITY_NEG`）：

```
photorealistic, photo, realistic skin texture, blurry, lowres, jpeg artifacts,
deformed face, asymmetric eyes, distorted mouth, extra fingers, bad hands,
text, watermark, signature, multiple people, cropped head,
gradient background, textured background, patterned wall, scenery, landscape,
bokeh, room interior, drop shadow, cast shadow, props, furniture,
3d render, plastic doll
```

带 `--features` 时再追加 `IDENTITY_NEG`：

```
different person, generic anime face, wrong hairstyle, missing glasses,
changed face shape, different hair color, unrecognizable identity
```

这套负向词是从 v1.4 的实际翻车里长出来的，别删：

- `photorealistic / photo / realistic skin texture` —— 不压就会保留真人写实质感，卡通感不够
- `asymmetric eyes / distorted mouth` —— 卡通大眼最容易崩对称
- `cropped head / multiple people` —— img2img 在 strength 偏高时会切头或复制出第二个人
- `text / watermark` —— 出图带水印/文字会破坏透明抠图
- `3d render / plastic doll` —— 会跑成黏土风，与扁平赛璐璐不搭
- `gradient / textured / scenery / bokeh / drop shadow / props`（v1.2 补）—— 任何非纯色背景都会让抠图带毛边
- `different person / generic anime face / missing glasses / changed face shape`（v1.3 补）—— 不压就会出"通用动漫脸"，跟本人对不上

---

## 3. 参数配方

| 场景 | strength | steps | cfg | 备注 |
| --- | --- | --- | --- | --- |
| 照片直接转卡通（v1.4 实测） | 0.65 ~ 0.68 | 20 | 7.0 | 保留五官与发型，卡通化明显 |
| 只做表情变化（以定妆照为 init） | 0.45 ~ 0.55 | 20 | 7.0 | 一致性最高，表情差异靠 prompt |
| 画风大改（水彩/厚涂/像素） | 0.72 ~ 0.82 | 24 | 7.0~8.0 | 会牺牲部分相似度 |
| 追加要求后"不像本人" | 降到 0.50 ~ 0.58 | 20 | 7.0 | 相似度问题几乎都是 strength 过高 |

其它约定：

- **sampler**：`euler` 最稳；`dpm++2m` 细节更多但偶发糊脸
- **尺寸**：`832×1024`（或 `832×1216`）；**同一批必须完全一致**，否则抠图归一化再对齐也是补救
- **seed**：基准 `20261112`，第 i 个表情用 `seed + i*13`（v1.4 配方）。固定 seed 是"重做单张但不改变其它张"的前提
- **count-each**：给客户看小样时可传 2~3，出多张候选再挑

---

## 4. locmodel MCP 调用映射

本地引擎（通过 `locmodel-image` MCP）：

| 目的 | MCP 工具 | 关键参数 |
| --- | --- | --- |
| 照片 → 卡通（保构图） | `redraw_image` | `init_image=照片`、`prompt=清单 prompt`、`strength=0.66`、`seed=清单 seed` |
| 局部改（只改眼睛/嘴） | `edit_image` | `init_image`、`prompt`（描述该区域**要出现什么**）、`regions` 或 `mask_image` |
| 纯文生图（无照片） | `generate_image` | `prompt`、`aspect="3:4"`、`count=2`、`seed` |
| 看引擎/模型状态 | `engine_discover` / `list_models` / `locmodel_status` | — |
| 装载 flux.2 等模型 | `load_model` | 模型名见 `list_models` 输出 |

注意：`edit_image` 只有 `can_region_edit=true` 的模型（如 qwen-image-edit）才真正做局部重绘，flux.2 / z_image_turbo 走的是整图路径——想精确改局部就别指望它。

---

## 5. 用线上 / WorkBuddy 技能时的对应关系

| 本 skill 里的东西 | 线上路线的对应做法 |
| --- | --- |
| `--manifest-only` 产出的 prompt | 直接粘进「图片转二次元/卡通」skill 的输入框 |
| `--desc` | 换成该 skill 的"角色描述/主体描述"字段 |
| 表情差异 | 在该 skill 的"表情/动作"字段逐条填上表的中文名 |
| 固定 seed | 若该 skill 支持种子就填 `20261112`，不支持就多出几张人工挑 |
| 回传命名 | 一律存成 `raw/<key>.png`，后续 cutout 不再关心来源 |

---

## 6. 质量判断标准（给客户看小样时说这些）

拿小样前自己先按这 6 条筛，不合格的直接重做，别把半成品推给客户：

1. **像本人（硬指标）**：用 `identity.py --compare-sheet` 打分，≥80 才算过；65~80 先问客户，<65 直接重做。五官布局、发型、眼镜、脸型必须对得上 `features.json`
2. **眼睛对称**：双眼位置、大小、瞳孔方向不一致 → 废
3. **头部完整**：没有裁掉头顶、下巴、耳朵
4. **只有一个人**：出现第二张脸/多余肢体 → 废
5. **表情到位**：11 张之间看得出差别，不能全是同一个表情微调
6. **背景纯色**：只允许 magenta / green / blue / white 四选一，`make_sheet.py --check-bg` 出 FAIL 的一律不许发客户；渐变、场景、投影、道具都会被抠图放大成花边
---

## 7. 身份锁定（v1.3）

`scripts/identity.py` 把"像不像本人"从感觉变成可执行的三步：

| 步骤 | 命令 | 产出 |
| --- | --- | --- |
| 出骨架 | `identity.py --template --out features.json` | 待填的特征 JSON（字段齐全的空壳） |
| 校验 | `identity.py --validate features.json` | 必填项缺口清单，缺一项就不许往下走 |
| 出词 | `identity.py --emit features.json` | 英文 `desc` + 身份锁定正向词 + 负向词 + 中文特征总结 |
| 打分 | `identity.py --compare-sheet --photo me.jpg --cartoon assets/normal.png --features features.json --out compare.jpg --score-out score.json` | 原图/卡通并排对照图 + 相似度评分 |

特征 JSON 字段（必填 11 项，其余选填但强烈建议填满）：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `face_shape` | 脸型 | `oval` / `round` / `square` / `heart` |
| `skin_tone` | 肤色 | `fair warm beige` |
| `hair_length` | 发型长度 | `shoulder-length` |
| `hair_parting` | 分缝 | `middle part` |
| `hair_color` | 发色 | `black with brown highlights` |
| `hair_texture` | 发丝质感 | `straight` / `wavy` / `curly` |
| `bangs` | 刘海 | `side-swept bangs` |
| `eyebrows` | 眉形 | `soft arched` |
| `eyes` | 眼睛（含眼皮、瞳色、睫毛） | `double eyelid, dark brown iris, thick lashes` |
| `glasses` | 眼镜款式（无则写 `none`） | `thin gold round frame` |
| `nose` | 鼻型 | `small round tip` |
| `mouth` | 嘴/唇 | `full lower lip, slight smile` |
| `ears` | 耳 | `small, visible` |
| `marks` | 特殊标记（痣/纹/胡须/妆容） | `small mole under left eye` |
| `accessories` | 耳饰等配件 | `small silver stud earrings` |
| `clothing` | 服装领型、颜色、图案 | `white shirt, navy V-neck vest` |
| `age_feel` | 年龄感 | `late 20s, friendly` |
| `distinctive` | 一句话最能认出本人的点 | `round glasses + chin-length bob` |

评分权重：脸型 25 / 发型 25 / 眼睛 15 / 眼镜 15 / 肤色 10 / 服装 10。权重高的字段写错（比如漏了眼镜），分数掉得最快——**先核对这几项**。

*（内容由AI生成，仅供参考）*

