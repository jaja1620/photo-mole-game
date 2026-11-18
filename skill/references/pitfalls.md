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

**处理顺序**：

1. 先调 `--tol`（18 → 30 → 45 逐档试）
2. 还不行就让模型重出："`plain solid pastel background, no pattern`"
3. 最后兜底：装 `rembg` 用 u2net 模型抠（质量更高，但要额外依赖）

---

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

**标准应答**：先问是"五官不像"还是"风格不像"。

- 五官不像 → 降 `strength` 到 0.5~0.58，加强 `--desc` 的外观描述
- 风格不像 → 调 `--style`（水彩/厚涂/像素/国漫），`strength` 提到 0.72+

### 17. 关数改了但难度没跟着调

客户说"关数少一点"时，`target`（每关目标分）和 `interval` 也要同步降，否则一关打不完就死。经验：3~6 关的短档总时长控制在 60~120 秒。
*（内容由AI生成，仅供参考）*
