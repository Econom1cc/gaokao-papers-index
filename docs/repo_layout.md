# Repo 结构

- `papers/`：正式试卷文件，按年份-科目-地区-卷型组织。
- `data/coverage_matrix.csv`：年份 × 科目 × 地区覆盖矩阵。
- `data/missing_or_partial.csv`：缺失、占位或仅解析的记录。
- `data/paper_inventory.csv`：当前源文件清单与规范化目标路径草案。
- `data/region_paper_type_history.csv`：各地区逐年卷型变迁数据。
- `data/summary_*.csv`：按年份、科目、地区或年份+科目的缺失统计。
- `docs/region-paper-type-history.md`：地区卷型变迁与信息来源说明。
- `docs/missing-audit.md`：独立缺失审计。
- `docs/naming.md`：统一命名规范。
- `indexes/`：按科目、地区、年份、新老高考生成的多维索引。
- `schema/`：数据字段定义。
- `scripts/`：后续从 manifest 落盘和校验的工具。

本阶段只生成清单与骨架，不复制、不 OCR、不改名原文件。

## 英语科目存储例外

英语科目允许在标准 `PDF+md` 基础上增加听力音频，形成 `PDF+md+mp3`。建议放在同一试卷目录：

```text
papers/<年份>/英语/<地区或全国>/<卷型>/
├── YYYY_英语_..._原卷.pdf
├── YYYY_英语_..._OCR与考点.md
└── YYYY_英语_..._听力.mp3
```

听力原文或独立答案解析可作为额外 Markdown 文件保存。
