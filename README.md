# 中国高考试卷多维索引

本仓库当前保存 2008-2026 年全国九科试卷的元数据索引，不直接存放试卷原文件。

## 数据规模

- 年份：2008-2026
- 科目：九科
- 地区：31 个省级地区
- 索引记录：5301
- 已覆盖：4936
- 缺失或占位：363
- 老高考记录：4104
- 新高考记录：1197

## 索引入口

- [总索引](indexes/catalog.csv)
- [按科目](indexes/by-subject/)
- [按地区](indexes/by-region/)
- [按年份](indexes/by-year/)
- [按新老高考](indexes/by-exam-system/)
- [层级 JSON](indexes/hierarchy.json)

## 目录规范

```text
papers/<年份>/<科目>/<地区或全国>/<卷型>/<文件>
YYYY_科目_地区或卷型_材料类型_版本.ext
```

通用全国卷只保留在 `全国` 目录，省份覆盖通过 `data/coverage_matrix.csv` 映射。

## 数据说明

- `data/coverage_matrix.csv`：年份 × 科目 × 地区覆盖矩阵。
- `data/missing_or_partial.csv`：缺失或占位记录。
- `data/paper_inventory.csv`：源文件与建议目标路径。
- `data/summary_*.csv`：汇总统计。
- `docs/audit.md`：缺口审计报告。
- `docs/naming.md`：统一命名规范。

统计口径：通用全国卷覆盖计为已覆盖；占位文件不计为完整原卷。
