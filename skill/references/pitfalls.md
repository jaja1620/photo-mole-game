---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 798659b1f59514cb753b383c1f423b09_d5b6a0aae22511f1a768525400cd780f
    ReservedCode1: bRrP6YmG9nH43pw1FrIh8nuwWCrmk2Mkt1WcGTfguJRnUxtnDYUx4Exl5CVYssDNoPtVbvVJUIV1rG+WQi4DUX0M5s//8IEWNlR5RO7YMEoxR4X2xxaKzfuc/HNYl/0gHE1NxWvH+6c2LNhs2cqh9R4wQq6TJmftYssvb+tn2t+kJn3VOHaF5bdfhNI=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 798659b1f59514cb753b383c1f423b09_d5b6a0aae22511f1a768525400cd780f
    ReservedCode2: bRrP6YmG9nH43pw1FrIh8nuwWCrmk2Mkt1WcGTfguJRnUxtnDYUx4Exl5CVYssDNoPtVbvVJUIV1rG+WQi4DUX0M5s//8IEWNlR5RO7YMEoxR4X2xxaKzfuc/HNYl/0gHE1NxWvH+6c2LNhs2cqh9R4wQq6TJmftYssvb+tn2t+kJn3VOHaF5bdfhNI=
---

# 踩坑清单与发布流程

全部来自「敲谈姐儿 v1.4.0」实战，按"最容易踩"排序。

---

## 一、构建与素材

### 1. 单文件版只替换了第一处图片 → 彩蛋页破图

**现象**：单文件版主菜单正常，打通关后彩蛋页头像是空的（`naturalWidth === 0`）。

**原因**：内嵌 data URI 时用了只替换首个匹配的写法（`str.replace(a, b)`），而头像 `<img>` 在菜单、结果页、彩蛋页各出现一次，共 13 处。

**正确做法**：`str.replaceAll` 或带计数统计的循环替换，并在构建后断言：

- 静态外部引用数 = 0
- 运行时 `document.querySelectorAll('[src],[href]')` 里没有非 `data:` 开头项
- 关键图 `naturalWidth > 0`

### 2. 表情不做统一画布 → 换表情时人物上下乱跳

**现象**：看起来像"抖动 bug"，实际是素材尺寸不一致。

**原因**：AI 每次出图人物在画面里的占比不同，直接按原图绘制就会随表情"呼吸"。

**正确做法**：`cutout.py --normalize`，把所有人物的头顶/脚底锚到同一基准（640×800，头顶留 6%）。出图阶段就用固定尺寸也能大幅缓解。

### 3. 抠图带白边 / 抠掉半张脸

**原因**：背景与人物颜色接近、或背景复杂（照片实景）。floodFill 容差不够就会漏抠或过抠。

**v1.3 处理顺序**（禁止盲调参数）：

1. 先跑 `cutout.py --in raw/ --analyze`：看背景一致度、背景色、主体占比估计与推荐 `--tol` / `--bg-hex`；一致度 <0.55 说明背景不是纯色，直接回阶段 A 重生，别在此处硬抠
2. 按推荐值定参后再抠：`--tol <推荐值> --chroma auto`
3. 抠完立刻 `--verify`，逐项看 `cutout.report.json` 的 `keep_ratio` / `iou` / `hole_rate` / `edge_cut_ratio` / `comp2_ratio` / `dent_ratio` / `fg_ratio` / `edge_color_diff`；任何一项 FAIL 或出现 `dent`／`孔洞`／`连通域断裂`／`贴边裁切` 的 WARN，都按"主体被削"处理，回阶段 A 换与主体色差更大的纯色底重生
4. 单张复杂图仍不行时兜底：装 `rembg` 用 u2net 模型抠（质量更高，但要额外依赖）

详见下方 §18 / §19 / §21。

## 二、模板与配置

### 4. 正则替换误把文案拼重复

**现象**：首次改造模板时，菜单引导语出现两遍。

**原因**：用正则 `\s*` 匹配跨行内容，替换时把原行的一部分又拼回去。

**正确做法**：需要精确改写单行时，按**行号直接赋值**（读成 list、改指定 index、写回），不要用跨行正则。

### 5. `assert s.count(a) == 1` 因断行失败

**现象**：断言在替换前后失败，但肉眼看文本存在。

**原因**：源码在目标字符串中间换行（格式化断行），精确匹配过不了。

**正确做法**：改用 `re.sub` 配 `re.S`，或先 `\s+` 归一化再匹配。

### 6. 加难度档后该档变成 15 关

**原因**：`levelMax()` 逻辑是 `DIFF[diff].levels || LEVEL_MAX_ALL`，忘写 `levels` 就兜底成 15。

**正确做法**：新增档位必须给全 `name/levels/lives/interval/up/target/maxSame`，然后跑 `verify_game.py` 的 `#maxLvl` 断言。

### 7. 删表情后游戏里出现空白

**原因**：只改了 `expressions`，没改 `groups` / `deco`。

**正确做法**：三处同步；`verify_game.py` 会对 `KEYS` 全量断言 `naturalWidth > 0`，删漏了会直接报。

---

## 三、校验（Playwright）

### 8. Playwright 直接 `chromium.launch()` 卡 180 秒

**现象**：`msedge` 启动超时，或提示缺 `headless-shell`。

**正确做法**：用 CDP 连本机已装 Edge：

```python
proc = subprocess.Popen([msedge, "--headless=new", "--disable-gpu",
                         "--remote-debugging-port=9433",
                         "--user-data-dir=" + temp_profile, "about:blank"])
# 轮询 http://127.0.0.1:9433/json/version 直到就绪
br = pw.chromium.connect_over_cdp("http://127.0.0.1:9433")
page = br.contexts[0].new_page()       # 复用已有上下文
```

`verify_game.py` 已内置该逻辑。

### 9. 校验脚本在主会话里跑满 600 秒被杀

**正确做法**：长验证用 subprocess 起独立进程；结果先 `json.dump` → `flush` → `os.fsync` 落盘，**再** 关浏览器；脚本末尾 `os._exit(0)` 跳过清理挂起。

### 10. 大小写导致断言误报

**现象**：`kicker 不符`、`标语不符`，但页面上明明是想要的文字。

**原因**：CSS 有 `text-transform: uppercase`，`innerText` 返回大写。

**正确做法**：断言统一 `.strip().lower()` 比较。

### 11. 纸屑动画"看不见"但代码没问题

**正确做法**：不要靠截图目视。对 canvas 取 `getImageData`，抽样统计 `alpha > 8` 的像素数，`> 200` 即视为已绘制；同时断言粒子 `vy > 0`、初始多分布在 `y < 0`（从上方飘入）。

---

## 四、环境

### 12. `shell_executor` 报 `Field required`

**原因**：调用时漏了 `command` 字段。

**处理**：重新构造调用，别在原地重试同一空参数。

### 13. 本机 git 全局代理失效导致推送失败

**现象**：`git push` 卡住/失败，全局 `http.proxy` 指向一个已不可用的本地端口。

**正确做法**：单次绕过，不改全局配置：

```bash
git -c http.proxy= -c https.proxy= push
```

### 14. 中文文件名 + EOL 转换破坏字节一致性

**正确做法**：仓库根放 `.gitattributes`：

```
*.html -text
```

保证 HTML 不被 CRLF 转换，发布附件的 SHA256 才稳定可复现。

---

## 五、GitHub 发布流程

```bash
git init
git add -A
git commit -m "release: v1.4.0"
gh repo create <owner>/<repo> --public --source . --remote origin --push

git tag -a v1.4.0 -m "v1.4.0"
git -c http.proxy= -c https.proxy= push origin refs/tags/v1.4.0

gh release create v1.4.0 "<主题名>_单文件版_v1.4.0.html" \
   -R <owner>/<repo> --title "v1.4.0" --notes-file README.md --latest
```

要点：

- **产物名统一带版本号**：`index_v1.4.0.html`、`<主题名>_单文件版_v1.4.0.html`、`README_v1.4.0.md`。混版本名是后续最乱的来源
- Release 附件只放**单文件版**（目录版散文件不适合当附件）
- `--latest` 显式设置，避免 Latest 指到旧 tag
- 发布后回写校验信息：字节数 + SHA256，方便用户核对自己下载的文件

---

## 六、需求沟通（非技术，但最容易翻车）

### 15. 把"小样确认"省掉直接交付

客户对卡通形象的不满几乎 100% 发生在第一眼，不在玩法。**原图出来就先给客户看**，让客户三选一（全通过/全重做/选定重做），比做完游戏再返工便宜一个数量级。

### 16. 客户说"不像我"却没说改哪里

**标准应答**：先看 `identity.py --compare-sheet` 打出的对照图与相似度评分，把差异点摆出来再问是"五官不像"还是"风格不像"。

- 五官不像 → 先检查 `features.json` 里 `face_shape` / `hair_*` / `glasses` 是否写错或漏填，改正后重跑 `--emit` 与 `gen_expressions.py --features`；仍不像再把 `strength` 降到 0.5~0.58
- 风格不像 → 调 `--style`（水彩/厚涂/像素/国漫），`strength` 提到 0.72+

**禁止**跳过特征 JSON 直接改 prompt 猜——那正是 v1.2 之前"出来是通用动漫脸"的根因。

### 17. 关数改了但难度没跟着调

客户说"关数少一点"时，`target`（每关目标分）和 `interval` 也要同步降，否则一关打不完就死。经验：3~6 关的短档总时长控制在 60~120 秒。
---

## 七、v1.3 新增坑（抠图吞主体 / 卡通不像本人）

### 18. 抠图把衣服、配件、头发当成背景扣掉

**现象**：抠完人物还在，但白衬衫变透明、眼镜腿没了、头发边缘被啃掉一块、深色描边消失。

**原因**：色度键按"与背景色色差 < tol"判背景，人物身上与背景同色或相近的部位（白衣配白底、紫衣配品红底、肤色配浅粉底）会被整片删掉；四边 floodFill 兜底更会把贴边的衣服一起吃掉。

**v1.3 防线**（默认开启，别关）：

1. `cutout.py` 主体保护：色度键结果与 GrabCut 前景交叉校验，位于主体内部的被扣区域回填；`--no-protect` 只用于"确定背景就是主体色"的极端场景
2. `--verify` 的 `keep_ratio`（<0.95 WARN、<0.90 FAIL）、`iou`（<0.75 FAIL）、`hole_rate`（>1.5% WARN、>4% FAIL）、`dent_ratio`（0.48~0.50 WARN；>0.50 且 `dent_area_ratio` >1% 直接 FAIL，抓"头发两侧/肩部衣领被整块削掉"）就是专门抓这个；全部以**独立主体基准**为参照，禁止用抠图自己的 mask 自证
3. `--compare` 出原图/抠图并排图，人眼一眼能看出来

**处理**：FAIL 不要就地调 `--tol` 硬救（越救越啃）。回阶段 A 用与主体色差更大的纯色底重生（紫/粉衣→green，绿衣→blue，深色描边→white），再重跑分析 → 抠图 → 校验。

### 19. 不看报告就进构建

**现象**：`build_game.py` 直接报"缺 cutout.report.json"或"有 FAIL"，或更糟——没报错但游戏里人物缺块。

**原因**：v1.3 起 `build_game.py` 会校验 `assets/cutout.report.json` 存在且无 FAIL。跳过 `--verify` 等于把阶段 B 白做。

**正确做法**：抠完必看报告，`PASS` 才进阶段 C；确实要临时跳过（调试用）才加 `--allow-no-gate`，交付前必须去掉。

### 20. 卡通出来是"通用动漫脸"，跟本人没关系

**现象**：11 张表情风格统一、画得也好看，但用户第一眼说"这不是我"。

**原因**：只给了 `--desc "cute young woman, short hair"` 这类泛化描述，模型按平均动漫脸出图；发型、眼镜、脸型、痣等身份特征全丢了。

**正确做法**（v1.3 阶段 A0，红线 6）：

1. 先用图像理解**逐字段**看照片，`identity.py --template` 出骨架后填满：脸型、肤色、发型长度/分缝/颜色/刘海、眉、眼睛与眼皮瞳色睫毛、眼镜款式、鼻、嘴/唇、耳、特殊标记（痣/纹/胡须/妆容）、耳饰等配件、服装领型颜色图案、年龄感
2. `--validate` 必填齐备 → `--emit` 出英文 desc 与身份锁定词
3. 出图必须带 `--features features.json`（正向词锁"同发型、同眼镜、同脸型、可辨认是本人"，负向词压"不同的人、通用动漫脸、发型不符、缺眼镜、脸型改变"）
4. 出图后 `--compare-sheet` 打分：<65 直接重做，65~80 先问用户，≥80 才写 `gate.py --identity-*` 门禁

*（内容由AI生成，仅供参考）*

### 21. 校验拿自己的 mask 自证 → 头发/衣领被削还判 PASS（v1.3.0 修正）

**现象**：`--verify` 报"保留率 100%、孔洞 0%"、判定 PASS，可对照图上手能看出头发两侧被削、肩部衣领被抠掉（`05_angry.png` 就是这样漏过去的）。

**原因**：最初版口径是"先 GrabCut 抠出 mask，再把这份 mask 腐蚀一下当主体核心区，然后算核心区保住多少"——**自己判自己**。GrabCut 认错的时候，自证永远满分。

**v1.3.0 修正后的口径**（不许再退回自证）：

- 先建**独立主体基准**，与本次抠图的 `--chroma` / `--tol` 无关：
  `A = GrabCut 紧矩形初始化` ∩ `B = GrabCut 宽矩形初始化` → `agree`（保守主体）；
  `C = 四边泛洪反推`（与画幅四边连通且颜色相近的算背景）→ 只并入 `full` 作主体上界，画对照图黄线用；
  `core = erode(agree, 5% 短边)` → "必然属于主体"的核心区，算 `keep_ratio`
- 九项指标：`keep_ratio` / `iou` / `hole_rate` / `edge_cut_ratio` / `comp2_ratio` / `dent_ratio` / `dent_area_ratio` / `fg_ratio` / `edge_color_diff`
- 判级：`keep_ratio < 0.90` 或 `iou < 0.75` 或 `fg_ratio` 越界 → FAIL（退出码 2，列返工 key）；`dent_ratio > 0.50` 且 `dent_area_ratio > 1%`（或 `dent_ratio > 0.65`）→ 同样 FAIL；`keep_ratio < 0.95`、孔洞 1.5%~4%、第二大连通域 >5%、贴边裁切 >0.8%、边缘色差 <50、`dent_ratio` 0.48~0.50 → WARN 并写清原因
- `keep_ratio` 是粗筛哨兵，只对"整块被吃"敏感；**局部削切靠 `dent_ratio` 拦**（逐行左右边界相对滑动窗包络的最大内向凹陷 ÷ 主体高度），两项必须一起看

**复现注意**：GrabCut 内部是 KMeans 初始化，随机源会让同一张图抠出不同结果（实测前景占比能跳 27%~52%）。同一批图要一次跑完；复跑就整批重跑，别单挑一张；把背景做成纯色让色度键接管可以从根上消除随机性。

## 22. 深凹只判 WARN → 坏图绕过门禁进了游戏（v1.3.0 收紧）

**现象**：`05_angry.png` 右侧轮廓凹陷达主体高度 **0.54**（最深 642 像素，y≈613，缺口 21,356 像素 = 主体面积的 2.39%），头发两侧与肩部衣领已被削掉，肉眼一眼可见；但旧口径 `dent_ratio` 只有 >0.48 才 WARN、>0.65 才 FAIL，于是判 **WARN**。而 WARN 只提示、**不阻塞构建**，坏图照样进游戏。

**为什么会漏**：其余七项指标全都"看起来很好"——`keep_ratio 100%`、`hole_rate 0%`、`comp2_ratio 0%`、`edge_cut_ratio 0%`。削切是**局部内向凹陷**，不动核心区、不断连通域、不贴边，只有 `dent_ratio` 能看见；把它放在 WARN 档就等于没拦。

**v1.3.0 修正**：

- `dent_ratio > 0.50` **且** `dent_area_ratio > 1%`（缺口像素 ÷ 前景像素）→ **FAIL**，`cutout.py` 退出码 2、`summary.rework` 列出该 key，`build_game.py` 门禁拒构建；
- `dent_ratio > 0.65` → 无条件 FAIL（不论面积）；
- `dent_ratio` 0.48~0.50 → 仍 WARN，目视定夺；
- `keep_ratio < 0.95`、孔洞 1.5%~4%、连通域断裂（`comp2_ratio` > 5%）、贴边裁切 > 0.8%、边缘色差 < 50 → 维持 WARN。

**教训**：判定线要按"坏图能不能被拦住"来定，不是按"指标分布好不好看"。凡是肉眼一眼就废的形态（整块削进主体内部），必须落在 FAIL 档；WARN 只留给"需要人再看一眼"的边界情况。
