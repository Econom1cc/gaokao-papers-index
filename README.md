# 中国高考试卷多维索引

本仓库保存 2008-2026 年全国九科试卷的多维索引，并已开始收录实际试卷文件。当前已入库四川 2016-2025 六科试卷。

## 已入库试卷

- 四川 2016-2025：语数外物化生共 60 份
- PDF 原卷：60 份
- OCR 与考点 Markdown：60 份
- 英语听力 MP3：10 份
- 清单：`data/sichuan_2016_2025_manifest.csv`
- 文件说明：[papers/README.md](papers/README.md)

## 数据规模

- 年份：2008-2026
- 科目：语文、数学、英语、物理、化学、生物、政治、历史、地理
- 地区：31 个省级地区
- 索引记录：5301
- 已覆盖：4937
- 缺失或占位：363

## 说明文档

- [各地区卷型变迁](docs/region-paper-type-history.md)：按地区说明新老高考切换、语数外卷型、文综理综或选考卷型，并附官方改革依据。
- [九科缺失审计](docs/missing-audit.md)：单独统计覆盖、缺失、占位、缺失率和缺口分布。
- [统一命名规范](docs/naming.md)
- [Repo 结构说明](docs/repo_layout.md)

## 索引入口

- [可点击索引总导航](indexes/README.md)

## 目录规范

```text
papers/<年份>/<科目>/<地区或全国>/<卷型>/<文件>
YYYY_科目_地区或卷型_材料类型_版本.ext
```

通用全国卷只保留在 `全国` 目录，省份覆盖通过 `data/coverage_matrix.csv` 映射。

## 存储格式

- 常规科目：`PDF + md`
- 英语科目：`PDF + md + mp3`，其中 MP3 为听力音频；没有独立听力音频时只保留 `PDF + md`


## 数据文件

- `data/coverage_matrix.csv`：年份 × 科目 × 地区覆盖矩阵。
- `data/missing_or_partial.csv`：缺失或占位记录。
- `data/paper_inventory.csv`：源文件与建议目标路径。
- `data/region_paper_type_history.csv`：各地区逐年卷型变迁数据。
- `data/summary_*.csv`：汇总统计。
