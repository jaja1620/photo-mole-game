# photo-mole-game v1.3.0 发布说明

> 本文件为中文版；英文版见同目录 `RELEASE_NOTES_v1.3.0.en.md`（Release 页面顶部可一键切换）。

- 发布日期：2026-11-19
- 上一版本：v1.2.0
- 作者：JaJa
- 本版主题：**抠图不许吞主体、卡通必须像本人**——把实操中踩到的两类翻车（白衬衫变透明、发丝与衣领被当背景抠掉；卡通脸像"通用动漫脸"）固化为脚本校验与硬门禁。

---

## 1. 抠图加固（需求一）

### 1.1 新增 / 增强能力（`scripts/cutout.py`）

| 能力 | 参数 | 作用 |
| --- | --- | --- |
| 抠前分析 | `--analyze` / `--analyze-report <json>` | 统计背景一致度、主体占比与色距，给出建议 `--tol` / `--bg-hex`，避免凭感觉调参 |
| 主体保护（默认开启） | `--no-protect` 关闭，`--protect-radius <n>` 调带宽 | 色度键结果须与 GrabCut 前景**交叉校验**，落在主体内部的被扣区域自动回填，禁止把人物、衣服、配件当背景吞掉 |
| 抠后比对 | `--verify --report cutout.report.json` | 以**独立主体基准**（非自身 mask 自证）计算九项指标：`keep_ratio / iou / hole_rate / edge_cut_ratio / comp2_ratio / dent_ratio / dent_area_ratio / fg_ratio / edge_color_diff` |
| 对照图 | `--compare --compare-dir <dir>` / `--compare-only` | 输出原图 / 抠图并排对照与拼图 `*.compare.jpg`，肉眼一次判读 |
| 背景自适应 | `--chroma auto` | 自动读取 `manifest.json` 的 `bg.hex`，减少手填错色值 |

### 1.2 判级口径（脚本常量，非文档口径）

- `dent_ratio > 0.50` **且** `dent_area_ratio > 1%` → 直接 FAIL
- `dent_ratio > 0.65` → 直接 FAIL
- 软指标超过 `T_DENT_WARN = 0.48` 报 WARN
- 判 FAIL 时 `cutout.py` 以**退出码 2** 结束并列出返工 key，流水线无法继续构建

### 1.3 实测拦截证据

| 素材 | 结果 | 现象 |
| --- | --- | --- |
| `01_smug.png` | PASS | 主体完整，发丝与衣物边缘清晰 |
| `05_angry.png` | **FAIL**（退出码 2） | 头发两侧严重缺失、左侧肩部衣领被抠除——正是本版要拦的"人少了半个" |

### 1.4 SKILL.md 同步改写

- 红线由 4 条扩为 **6 条**，新增第 5 条「抠图禁止吞掉主体、衣服、配件；抠前必须分析参数，抠后必须比对」，列出白衣服变透明、眼镜没了、头边紫边、耳饰消失等典型翻车。
- 阶段 B 重写为四段：**抠前分析 → 定参 → 抠图 → 抠后比对**，明确"没看报告不许进构建"。

---

## 2. 卡通相似度加固（需求二）

### 2.1 新增 `scripts/identity.py`

| 能力 | 参数 | 作用 |
| --- | --- | --- |
| 特征骨架 | `--template --out <json>` | 22 键模板：`face_shape / skin_tone / hair_length / hair_parting / hair_color / bangs / hair_texture / eyebrows / eyes / glasses / nose / mouth / ears / marks / accessories / clothing / age_feel / distinctive` 等 |
| 完整性校验 | `--validate --features <json>` | 缺项逐条列出（实测缺 11 项时全部报出），禁止"几句大概描述"就出图 |
| 提示词导出 | `--emit --features <json>` | 输出英文 `desc`、**身份锁定正向词 11 条**、**负向词 9 条**（`different person / generic anime face / wrong hairstyle / missing glasses / changed face shape …`）与中文特征摘要 |
| 相似度评分 | `--compare-sheet --photo <原图> --cartoon <卡通>` | 生成原图 / 卡通对照拼图并给相似度评分，作为身份门禁数值来源 |

### 2.2 流水线接入

- **阶段 A0（新增）**：真人面部特征分析——出图前逐字段填模板，产出特征 JSON + 中文特征总结交用户确认。
- `gen_expressions.py --features <json>`：自动载入特征，把 `desc` 与身份锁定正向词写进每条表情提示词，负向词自动追加。
- `gate.py` 新增 `--identity-features / --identity-score / --identity-compare`；`build_game.py` 新增 `identity` 门禁：**评分 < 65 拒绝构建**，65–79 按差异点改特征重出，≥80 才可交用户确认。

---

## 3. 安装器（需求三）

- 单文件 exe：`photo-mole-game-installer.exe`（PyInstaller `--onefile --windowed`，内置载荷 19 文件 / 408,571 字节，目标机免装 Python）。
- Agent 支持 28 → **31 项**，新增：

| 显示名 | agent key | 默认目标目录 |
| --- | --- | --- |
| DeepSeek Harness | `deepseek-harness` | `~/.dsh/skills/photo-mole-game`（同时识别 `~/.dsh` 与项目内 `.dsh`） |
| Kimi | `kimi` | `~/.kimi/skills/photo-mole-game` |
| 豆包工作 | `doubao` | 手动导入：导出到 `~/photo-mole-game-import`（技能目录 + 技能 zip + 《豆包工作-手动导入指引.md》） |

- 豆包工作技能位于应用自管工作区（`%LOCALAPPDATA%/Doubao/User Data/Default/.doubao/agent_mode/workspace/.skills`），安装器不直接写入，改走"导出 + 手动导入"。

### 3.1 验收实测（全部基于最终 exe）

| # | 项目 | 结果 | 实测 |
| --- | --- | --- | --- |
| 1 | exe 构建 | 通过 | 10,436,783 字节，SHA256 `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| 2 | `--cli --list` | 通过 | 31/31 条目，已检测 7 / 未检测 24，WorkBuddy 显示已装 `v1.3.0`，退出码 0 |
| 3 | 真实安装（workbuddy → 临时目录） | 通过 | 19 文件 / 408,571 字节，`version: 1.3.0`，无 `__pycache__` |
| 4 | 幂等复跑 | 通过 | `[UNCHANGED]`，未产生 `.bak-*` |
| 5 | 篡改后覆盖 + 备份 | 通过 | `[UPDATE]`，生成 `photo-mole-game.bak-20261119-175450` |
| 6 | 豆包手动导入分支 | 通过 | 导出技能目录 + `photo-mole-game_v1.3.0.zip` + 导入指引 |
| 7 | GUI 启动 | 通过 | 标题 `photo-mole-game 技能一键安装器 v1.3.0`，出窗 1.07 秒 |
| 8 | 系统保护目录拒绝 | 通过 | `--dest C:/Program Files/pmfail` → `[ERR]`，退出码 1 |
| 9 | 非法 agent key 拒绝 | 通过 | `--agents no-such` → `[ERR]`，退出码 1 |

---

## 4. 与本地图形模型配合（本地出图全链路）

本技能**不绑定任何模型**，出图环节只走 HTTP 接口，所以既能用本机离线引擎，也能换线上模型。以下是三种可用接法、必须对齐的参数，以及模型出图后仍要过的三道闸。

### 4.1 三条接入路径

| 路径 | 做法 | 适用场景 |
| --- | --- | --- |
| **A. 全自动本地批量（推荐）** | 本地先起 `sd-server`（stable-diffusion.cpp 内核，A1111 兼容接口），脚本直接给 `--endpoint http://127.0.0.1:8790`，11 张表情一次跑完 | 引擎已常驻、要一条命令出全套图 |
| **B. MCP 逐张生成** | 先 `gen_expressions.py --manifest-only` 导出 `raw/manifest.json`（每张带 prompt / negative / seed），再由 agent 调 `locmodel-image` 的 `redraw_image(init_image=照片, prompt=…, negative_prompt=…, strength=0.66, seed=…)`，存成 `raw/<key>.png` | 引擎由 MCP 托管、需要模型优先级自动选择或随时切模型 |
| **C. 线上模型降级** | 同一份 manifest 清单交给线上图生图 / 图生卡通模型，按 `raw/<key>.png` 回传 | 本机无 GPU 或没有本地引擎 |

### 4.2 引擎就绪检查（MCP 路线先做这四步）

| 工具 | 用途 |
| --- | --- |
| `locmodel_status` | 看端口、已载模型、引擎默认参数、显存与尺寸策略 |
| `engine_discover` | LocModel 重启后端口可能变化，重新发现 |
| `engine_doctor` | 出图失败先自查：Python、引擎连通、模型、显存厂商、输出目录可写、辅助工具 |
| `list_models` / `list_edit_models` / `load_model` | 列可用模型、按需切换（切换会等引擎确认载入） |

可用模型示例：**flux2-klein（flux.2 klein 4B）** 与 **z_image_turbo（z_image_turbo-Q4_K）**，两者都支持 img2img；量化档越低越省显存。参考速率：1024×1024 单张约 20–60 秒（中端显卡）。

### 4.3 必须对齐的出图参数

| 参数 | 表情（`gen_expressions.py`） | 惊喜图（`gen_prize.py`） | 说明 |
| --- | --- | --- | --- |
| `--endpoint` | `http://127.0.0.1:8790` | 同 | 留空即只导出清单，不会静默改走线上 |
| `--strength` | `0.66`（常用 0.55–0.75） | `0.80`（半身扩展身建议 0.78–0.88） | 太低不变、太高脱离本人 |
| `--steps` | `20` | `24` | turbo 类模型可再降 |
| `--sampler` | `euler` | `euler` | 与引擎侧一致 |
| `--cfg` | `7.0` | `7.0` | 蒸馏模型按模型卡另行下调 |
| `--width` / `--height` | `832 × 1024` | `832 × 1216` | 8 的倍数 |
| `--seed` | `20261112`（每张 = seed + idx×13） | `20261118` | 固定种子可复现 |
| `--bg` | `magenta`（#FF00FF） | 不涉及 | 四选一：magenta / green / blue / white |

惊喜图另加：`--init assets/normal.png`（以定稿表情人物为基准扩全身）、`--poses 3`、`--per-diff normal,hard,hell`。

### 4.4 img2img 的输入约束（不遵守必然掉分）

1. **init_image 必须是被拍者本人**：表情阶段用用户照片，惊喜图阶段用 `assets/normal.png`；拿别人的图或二次压缩过的图当起点，身份锁定词救不回来。
2. **必须带 `--features`**：`features.json` 把 22 键真人特征写进 `desc`、身份锁定正向词与负向词。不带就是"通用动漫脸"，`identity.py` 评分几乎必然跌破 65，`build_game.py` 直接拒绝构建。
3. **背景只能纯色**：模型出图时的背景描述已内置在 prompt 里（`{bg} background (#HEX), completely uniform fill, no gradient, no vignette, no shadow, no props`），色值会写进 `raw/manifest.json` 的 `bg.hex`，阶段 B 抠图用 `--chroma auto` 直接读。
4. **不要手改脚本导出的 prompt**：MCP / 线上路线尤其如此，删掉背景描述或负向词，抠图与一致性两处都会翻车。

### 4.5 分工边界（模型只负责"画"）

| 环节 | 由谁完成 | 是否联网 |
| --- | --- | --- |
| 表情 / 惊喜图出图 | 本地扩散模型（或线上模型） | 本地不联网 |
| 抠图、统一画布 | `cutout.py`（色度键 + GrabCut + 连通域，本地 CPU） | 否 |
| 身份评分、对照图 | `identity.py`（本地图像指标） | 否 |
| 门禁、构建、回归 | `gate.py` / `build_game.py` / `verify_game.py` | 否 |

技能**不写引擎配置**：不改 LocModel 的 `config.json`，模型加载与显存策略由引擎 / MCP 侧决定；参数通过 HTTP 载荷按任务下发。

### 4.6 模型出图后的三道闸（缺一即拒建）

1. **小样闸**：`make_sheet.py` 拼小样并跑 `bgcheck`（背景纯色检查），FAIL 的小样不得当作"可通过"交给用户。
2. **身份闸**：`identity.py --compare-sheet` 出原图 / 卡通对照并评分——≥80 可交用户确认，65–79 按差异点改特征重出，<65 由 `build_game.py` 拒绝构建。
3. **抠图闸**：`cutout.py --verify` 出 `cutout.report.json`，九项指标有任一项 FAIL（含 `dent_ratio` 判级）即退出码 2，流水线停在此处。

### 4.7 快速自检命令

```bash
# 引擎侧
locmodel_status            # 或直接看 http://127.0.0.1:8790 是否可访问
engine_doctor              # 出图失败先跑这个

# 技能侧
python scripts/identity.py --template --out features.json     # 1. 先产特征骨架
python scripts/gen_expressions.py --photo me.jpg --out raw/ \
    --endpoint http://127.0.0.1:8790 --features features.json \
    --strength 0.66 --two-stage                               # 2. 本地批量出图
python scripts/make_sheet.py --in raw --out raw/sheet.jpg --cols 4   # 3. 小样（给用户看）
python scripts/identity.py --compare-sheet --photo me.jpg \
    --cartoon assets/normal.png --features features.json \
    --out identity.compare.jpg --score-out identity.score.json       # 4. 身份评分
python scripts/cutout.py --in raw/ --analyze                  # 5. 抠前分析
python scripts/cutout.py --in raw/ --out assets/ --normalize \
    --chroma auto --tol <分析推荐值> --verify --compare        # 6. 抠图 + 报告
```

---

## 5. 交付物清单

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,436,783 | `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| `photo-mole-game_v1.3.0.zip` | 155,111 | `4A63F892FB07F2D7239DF1274D7BF7465D779F80E169655060249F973858035E` |
| `CHECKSUMS-v1.3.0.txt` | 见文件 | 含包内 19 文件逐项哈希 + 交付物哈希 |
| `RELEASE_NOTES_v1.3.0.md` | 本文件 | — |

技能包：19 文件 / 408,571 字节，`manifest.json` 逐文件校验；zip 根目录 `photo-mole-game/`，排除 `__pycache__` / `*.pyc`，与源目录逐文件大小、哈希一致。

---

## 6. 升级与回滚

- 升级：双击 exe，勾选目标 Agent → 一键安装（覆盖前自动备份为 `photo-mole-game.bak-时间戳`）；或解压 zip 后把 `photo-mole-game/` 复制进 `<agent>/skills/`。
- 回滚：删掉安装目录，把 `photo-mole-game.bak-*` 改回原名；或改取 v1.2.0 全套。
- 校验：`Get-FileHash <文件> -Algorithm SHA256` 比对第 5 节与 `CHECKSUMS-v1.3.0.txt`。

## 7. 已知限制

- 抠图判级为启发式阈值：极浅发色压白底、半透明衣物等极端素材可能仍需人工看对照图复核。
- 卡通相似度评分由图像侧指标给出，属辅助门禁，最终"像不像"仍以用户确认为准。
- 豆包工作不写入应用工作区，需按导出指引手动导入一次。
- 本地出图速度强依赖显卡与量化档，本版未给出统一基准；大批量建议先用 `--only` 单张试参再全量。
