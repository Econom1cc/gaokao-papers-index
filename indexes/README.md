# 多维度索引

同一份覆盖记录被切成四套索引：

- `by-subject/`：按九科拆分。
- `by-region/`：按 31 个省级地区拆分。
- `by-year/`：按 2008-2026 年拆分。
- `by-exam-system/`：按 `新高考`、`老高考`拆分。
- `catalog.csv`：完整总索引。
- `catalog.jsonl`：逐行 JSON，适合程序读取。
- `hierarchy.json`：按科目、地区、年份和高考模式嵌套。

相关说明：

- [各地区卷型变迁](../docs/region-paper-type-history.md)
- [九科缺失审计](../docs/missing-audit.md)
