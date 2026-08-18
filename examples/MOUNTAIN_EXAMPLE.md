# Example B — 远山 + 溪流 + 左右松树

这个示例只说明**宏观顺序和 Pass 2 层级**。

## Pass 1 Macro Units

```text
mountain_mass
river_spine
left_pines
right_pines
left_bank_rocks
right_bank_rocks
left_foreground_flora
right_foreground_flora
```

不要用“山体矩形”吸收矩形范围里的松树。山和松树应通过 token ownership 分开。

## Pass 2

`mountain_mass`：

```text
silhouette
→ major left ridge
→ center ridge
→ right ridge
→ minor internal cracks/details
```

`left_pines`：

```text
tall pine trunk + major branch flow
middle pine trunk + major branch flow
small pine trunk + major branch flow
→ needle/detail terminals
```

## Macro order

AI 可以给默认：

```text
mountain_mass → river_spine → left_pines → right_pines → banks → foreground
```

用户在 V4/V5 Studio 中可以改成：

```text
mountain_mass → left_pines → right_pines → river_spine → banks → foreground
```

这是 presentation override，不是重新做语义分析。
