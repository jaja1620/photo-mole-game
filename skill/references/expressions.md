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

**正向**（`gen_expressions.py` 内 `PROMPT_POS`）：

```
chibi anime cartoon portrait of {desc}, {expr}, upper body head and shoulders,
facing viewer, centered, {style}, thick clean outline, soft cel shading,
flat pastel background, high quality, sharp focus
```

- `{desc}` = `--desc`，人物外观描述，**角色一致性主要靠它**
- `{expr}` = 上表的表情描述
- `{style}` = `--style`，默认 `kawaii flat illustration style, 2d anime, vivid but soft colors`

**负向**（`PROMPT_NEG`）：

```
photorealistic, photo, realistic skin texture, blurry, lowres, jpeg artifacts,
deformed face, asymmetric eyes, distorted mouth, extra fingers, bad hands,
text, watermark, signature, multiple people, cropped head, cluttered background,
3d render, plastic doll
```

这套负向词是从 v1.4 的实际翻车里长出来的，别删：

- `photorealistic / photo / realistic skin texture` —— 不压就会保留真人写实质感，卡通感不够
- `asymmetric eyes / distorted mouth` —— 卡通大眼最容易崩对称
- `cropped head / multiple people` —— img2img 在 strength 偏高时会切头或复制出第二个人
- `text / watermark` —— 出图带水印/文字会破坏透明抠图
- `3d render / plastic doll` —— 会跑成黏土风，与扁平赛璐璐不搭

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

1. **像本人**：五官布局与发型可辨认（相似度是这类游戏唯一的"诚意指标"）
2. **眼睛对称**：双眼位置、大小、瞳孔方向不一致 → 废
3. **头部完整**：没有裁掉头顶、下巴、耳朵
4. **只有一个人**：出现第二张脸/多余肢体 → 废
5. **表情到位**：11 张之间看得出差别，不能全是同一个表情微调
6. **背景干净**：单色或简单渐变，否则抠图会带毛边
*（内容由AI生成，仅供参考）*
