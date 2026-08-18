# APainting 图片执行模式（给 Codex）

这份文件是**已经批准的运行流程**。当用户附加一张图片并要求“生成 APainting 动画 / 加载到 Studio”时，任务是**运行现有程序处理图片**，不是设计新功能，也不是修改架构。

## 最重要的执行规则

1. **不要先写设计规格、brainstorming、implementation plan、review document 或 worktree。**
2. **不要询问用户“7 个单元是否可以”“是否开始实施”之类的确认。** 直接根据图片做合理判断并执行到可播放预览。
3. 除非命令实际报错、输入文件无法访问或数据契约无法满足，否则不要停下来等待用户。
4. Pass 1 默认使用 `token_ids`。**不要为了语义主体手工画 polygon / corridor / bbox。** `unit_map.png` 只是 token 无法表达时的备用方案。
5. `bbox_hint` 只用于 crop/debug，永远不能决定 path ownership。
6. Pass 2 只能解释一个已归属 Unit 内部怎么画，不能重新分配 ownership。
7. 每一步都用程序的 `validate` 命令判断是否通过，不要凭感觉写长篇审查文档。
8. 如果验证失败，只修当前失败层；不要重新设计整个 pipeline。

---

# 一次完整任务

假设用户附加的图片在本地可访问为：

```text
D:\Images\input.png
```

工程目录是 APainting 仓库根目录。

## Step 0 — 创建 run

```powershell
apainting codex-start "D:\Images\input.png" --out runs\latest
```

然后**立即读取**：

```text
runs/latest/CODEX_RUNBOOK.md
```

该文件是针对当前图片自动生成的执行清单，里面会包含尺寸、path 数、token 数和当前 atlas 文件。

---

## Step 1 — Pass 1：识别大主体 + Visual Token ownership

必须看：

```text
runs/latest/assets/source.png
runs/latest/analysis/source_grid.png
runs/latest/analysis/visual_token_atlas.png
runs/latest/analysis/token_tiles/*.png
```

然后写：

```text
runs/latest/scene_plan.json
```

### 思考方式

不要问：

> 这个矩形属于谁？

要问：

> 这些 C#### Visual Token 在视觉上属于哪个 Drawing Unit？

推荐先识别 5–10 个“可以连续完成的大绘画单元”，然后把 token 分给它们。

### 正确示例：溪流花枝图

宏观 Unit 可以是：

```text
upper_flowering_branch
river_corridor
left_bank_flora_rocks
right_bank_irises_rocks
stepping_stones
water_lily_cluster
lower_right_foreground_flora
```

注意：这只是**示例粒度**，不是按名字硬套下一张图。

示意 JSON：

```json
{
  "coordinate_space": "normalized_1000",
  "style": "botanical_single_line_stationery",
  "strategy": "scaffold_then_local_completion",
  "unit_map_path": null,
  "units": [
    {
      "id": "upper_flowering_branch",
      "label": "上方开花主枝",
      "kind": "upper_branch",
      "root": {"x": 930, "y": 260},
      "direction": "along_structure",
      "grammar": "branch_growth",
      "priority": 0,
      "layer": 0,
      "subdivide": true,
      "notes": "从右侧木质主干向左生长",
      "mask_value": null,
      "token_ids": ["C0003", "C0007", "C0011"],
      "bbox_hint": null
    }
  ],
  "dependencies": [],
  "rationale": "宏观单元用于连续绘制，不追求恢复唯一真实历史。"
}
```

`C0003/C0007/...` **只是格式示例，实际必须从当前图片 atlas 读取，绝对不能照抄。**

### 不要这样做

```text
upper_flowering_branch bbox = 上半区
→ 把 bbox 里的 path 全归进去
```

也不要：

```text
为了做 mask，手工写几十条坐标走廊
→ 不断修 polygon
→ 花 20 分钟调语义边界
```

默认应该直接利用 Visual Token Atlas：

```text
C0012 + C0018 + C0021 → upper_flowering_branch
C0045 + C0049          → river_corridor
...
```

不确定 crossing token 可以暂时不分。

完成后立即运行：

```powershell
apainting validate runs\latest --stage pass1
```

### Pass 1 通过标准

- `weighted token coverage >= 0.95`
- 没有同一个 token 同时属于两个 Unit
- 没有不存在的 token ID
- 每个 Unit 有可执行 ownership 证据

如果失败，程序会生成：

```text
runs/latest/analysis/pass1_unassigned_tokens.png
```

只检查这张图里的未归属 token，补齐后再次验证。**不要重新做全部主体识别。**

Pass 1 通过后程序还会生成：

```text
runs/latest/analysis/unit_views/*.png
```

给第二遍 AI 使用。

---

## Step 2 — Pass 2：每个 Unit 内部结构

看：

```text
runs/latest/analysis/unit_views/*.png
```

再结合原图，写：

```text
runs/latest/structure_plan.json
```

Pass 2 只回答：

```text
主干/主轮廓是什么？
主要分枝是什么？
二级结构是什么？
花/叶/细节挂在哪里？
哪些内容属于同一 focus_group？
这个局部从哪里往哪里推进？
```

### 植物示例

```text
right_bank_irises
├─ root_base                   backbone
├─ tall_leaf_fan               primary_structure
├─ flower_stem_group           primary_structure
├─ iris_flower_heads           terminal
└─ local_accent                由 compiler 在局部线条后处理
```

示意 JSON：

```json
{
  "coordinate_space": "normalized_1000",
  "units": [
    {
      "unit_id": "right_bank_irises",
      "guides": [
        {
          "id": "iris_main_growth",
          "role": "backbone",
          "points": [
            {"x": 760, "y": 900},
            {"x": 755, "y": 760},
            {"x": 770, "y": 610}
          ],
          "focus_group": "iris_main_growth",
          "order": 0,
          "progress_start": 0.0,
          "progress_end": 1.0,
          "influence_radius": 80,
          "notes": "根部到主要花茎"
        }
      ],
      "notes": "只解释 right_bank_irises 内部，不修改 macro ownership"
    }
  ],
  "rationale": "结构先于 terminal，颜色跟随局部完成。"
}
```

完成后立即运行：

```powershell
apainting validate runs\latest --stage pass2
```

如果只提示某个 Unit 缺 guides，只补这个 Unit，不要重做 Pass 1。

---

## Step 3 — 一条命令完成编译、渲染、抽帧

```powershell
apainting finalize runs\latest --duration 18 --max-height 1080
```

它会：

```text
validate Pass 2
→ compile
→ 检查 path grounding
→ render preview
→ 提取 1s / 3s / 5s
→ final validation
```

重点检查：

```text
runs/latest/outputs/inspection_1_3_5.png
runs/latest/outputs/contact_sheet.png
runs/latest/analysis/uncertain_paths.png   (如果存在)
```

只处理明确失败：

- 未画区域提前泄露；
- 花色先于所属花的结构；
- 花/叶 terminal 明显早于支撑枝；
- 一个局部刚开始就跳到远处；
- ownership 肉眼明显错误。

不要因为“还能更完美”就进入无限调参。

---

## Step 4 — 加载 Studio

```powershell
apainting serve runs\latest --port 8000
```

最终回复用户只需要：

```text
已完成。
Studio: http://127.0.0.1:8000/
Preview: runs/latest/outputs/replay.mp4
1/3/5s: runs/latest/outputs/inspection_1_3_5.png
Path grounding: xx.x%
Unresolved paths: N
Macro order: A → B → C → ...
```

不要再要求用户批准实现计划。

---

# 山谷图示例：如何判断 Macro Units

对于“远山 + 溪流 + 左右松树 + 前景植物”的图，可以考虑：

```text
mountain_mass
left_pines
right_pines
river_spine
left_bank_rocks
right_bank_rocks
left_foreground_flora
right_foreground_flora
```

AI 默认顺序可以是：

```text
mountain_mass
→ river_spine
→ left_pines
→ right_pines
→ banks
→ foreground
```

用户之后可以在 Studio 改成：

```text
mountain_mass
→ left_pines
→ right_pines
→ river_spine
→ banks
→ foreground
```

这只是 `playback_settings.json.unit_order` 的播放层修改，**不能因此改 scene_plan ownership 或 structure_plan。**

---

# 故障恢复表

| 现象 | 只修哪里 | 不要做什么 |
|---|---|---|
| 某些线属于错误主体 | `scene_plan.json.token_ids` | 不调 bbox 距离 |
| coverage < 95% | 看 `pass1_unassigned_tokens.png`，只补漏 token | 不重画全图 polygon |
| 大主体正确但内部乱跳 | `structure_plan.json` | 不重新分主体 |
| 花色提前出现 | 检查所属 Unit / focus group / accent owner | 不全局延后所有颜色 |
| 用户想改山/树/溪流大顺序 | Studio / `playback_settings.json` | 不修改 AI ownership |
| render 成功但 1/3/5s 不自然 | 修最小责任层后重新 finalize | 不重新写设计文档 |
| FFmpeg 不可用 | 先保留 OpenCV MP4 预览 | 不阻塞整个分析流程 |

