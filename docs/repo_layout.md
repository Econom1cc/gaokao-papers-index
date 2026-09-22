# Repo 结构

- `papers/`：正式试卷文件，按年份-科目-地区-卷型组织。
- `data/coverage_matrix.csv`：年份 × 科目 × 地区覆盖矩阵。
- `data/missing_or_partial.csv`：缺失、占位或仅解析的记录。
- `data/paper_inventory.csv`：当前源文件清单与规范化目标路径草案。
- `data/region_paper_type_history.csv`：各地区逐年卷型变迁数据。
- `data/summary_*.csv`：按年份、科目、地区或年份+科目的缺失统计。
- `docs/region-paper-type-history.md`：地区卷型变迁与权威来源说明。
- `docs/missing-audit.md`：独立缺失审计。
- `docs/naming.md`：统一命名规范。
- `indexes/`：按科目、地区、年份、新老高考生成的多维索引。
- `schema/`：数据字段定义。
- `scripts/`：后续从 manifest 落盘和校验的工具。

本阶段只生成清单与骨架，不复制、不 OCR、不改名原文件。
