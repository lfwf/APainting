# Example A — 开花枝 + 溪流 + 岸边植物

这个示例只说明**决策方式和粒度**，不能复制 token ID 或坐标到其他图片。

## Pass 1

合理的 Macro Drawing Units：

1. `upper_flowering_branch` — 上方木质开花枝，入口在右侧，沿主枝向左生长。
2. `river_corridor` — 溪流与主要岸线关系，远到近。
3. `left_bank_flora_rocks` — 左岸主要花草与紧密岩石关系。
4. `right_bank_irises_rocks` — 右岸鸢尾与其承托岩石。
5. `stepping_stones` — 溪流中的踏脚石，远到近。
6. `water_lily_cluster` — 左下睡莲/荷叶局部。
7. `lower_right_foreground_flora` — 右下前景植物。

核心不是写 bbox，而是从 Visual Token Atlas 逐个确认：

```text
C#### → upper_flowering_branch
C#### → river_corridor
...
```

交叉处如果一个 token 同时包含两类语义，先留空，Pass 1 validator 会把它放进 `pass1_unassigned_tokens.png`。

## Pass 2

`upper_flowering_branch`：

```text
main woody arc                 backbone
├─ hanging primary branch     primary_structure
│  ├─ small twigs             secondary_structure
│  └─ flower/leaf terminals   terminal
├─ left primary branch        primary_structure
└─ right local terminals      terminal
```

`right_bank_irises_rocks`：

```text
root/base
→ tall leaves + main flower stems
→ secondary leaves
→ iris heads
→ local accent
```

## 验收

1 秒：应主要看到上方枝/构图结构，不应孤立出现下方鸢尾粉色。
3 秒：当前局部应接近完成，不应出现大量“花瓣一半”。
5 秒：进入溪流/岸边下一阶段时，不应突然同时冒出多个远距离前景细节。
