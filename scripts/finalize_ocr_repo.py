#!/usr/bin/env python3
"""合并 OCR 分片进度，校验文件，并更新仓库统计说明。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ocr_all_papers import ROOT, build_records, load_progress, load_rows, save_progress, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, nargs="+", required=True)
    parser.add_argument("--output-progress", type=Path, default=ROOT / ".ocr-progress.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "full_paper_manifest.csv")
    return parser.parse_args()


def patch_markdown_metadata(path: Path, record: dict[str, object]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^exam_mode:.*$", f"exam_mode: {record['exam_mode']}", text)
    text, count2 = re.subn(r"(?m)^comprehensive:.*$", f"comprehensive: {record['comprehensive']}", text)
    text = re.sub(r"(?m)^- 考试模式：.*$", f"- 考试模式：{record['exam_mode']}", text)
    text = re.sub(r"(?m)^- 综合科目：.*$", f"- 综合科目：{record['comprehensive']}", text)
    if record["comprehensive"] == "无":
        text = re.sub(r"(?m)^> 老高考综合科目.*\n?", "", text)
    if count or count2:
        path.write_text(text, encoding="utf-8")


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def main() -> int:
    args = parse_args()
    records = build_records(load_rows(ROOT / "data" / "paper_inventory.csv"))
    by_key = {str(record["key"]): record for record in records}
    progress: dict[str, dict[str, object]] = {}
    for shard_path in args.progress:
        for key, item in load_progress(shard_path).items():
            if key in by_key:
                progress[key] = item

    for key, record in by_key.items():
        item = progress.get(key, {})
        pdf = Path(record["pdf_path"])
        md = Path(record["md_path"])
        if item.get("status") == "done" and pdf.exists() and md.exists():
            patch_markdown_metadata(md, record)
            item["year"] = record["year"]
            item["subject"] = record["subject"]
            item["area"] = record["area"]
            item["paper_type"] = record["paper_type"]
            item["pdf_path"] = str(pdf)
            item["md_path"] = str(md)
            item["mp3_path"] = str(record["mp3_path"]) if Path(record["mp3_path"]).exists() else ""
            continue
        if pdf.exists() and md.exists():
            patch_markdown_metadata(md, record)
            progress[key] = {
                "key": key, "status": "done", "year": record["year"], "subject": record["subject"],
                "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "existing",
                "pages": 0, "pdf_path": str(pdf), "md_path": str(md),
                "mp3_path": str(record["mp3_path"]) if Path(record["mp3_path"]).exists() else "",
                "note": "由已有文件补记",
            }
        else:
            progress[key] = {
                "key": key, "status": "failed", "year": record["year"], "subject": record["subject"],
                "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "",
                "pages": 0, "pdf_path": str(pdf), "md_path": str(md), "mp3_path": "",
                "note": "分片结束后仍缺少 PDF 或 Markdown",
            }

    save_progress(args.output_progress, progress)
    write_manifest(args.manifest, records, progress)

    statuses = Counter(str(item.get("status", "unknown")) for item in progress.values())
    methods = Counter(str(item.get("ocr_method", "")) for item in progress.values() if item.get("status") == "done")
    years = Counter(str(by_key[key]["year"]) for key, item in progress.items() if item.get("status") == "done")
    subjects = Counter(str(by_key[key]["subject"]) for key, item in progress.items() if item.get("status") == "done")
    pdf_count = sum(1 for record in records if Path(record["pdf_path"]).exists())
    md_count = sum(1 for record in records if Path(record["md_path"]).exists())
    mp3_count = sum(1 for record in records if Path(record["mp3_path"]).exists())
    papers_size = directory_size(ROOT / "papers")
    summary = {
        "exam_sets": len(records),
        "status": dict(statuses),
        "methods": dict(methods),
        "pdf": pdf_count,
        "markdown": md_count,
        "mp3": mp3_count,
        "papers_size_bytes": papers_size,
        "by_year": dict(sorted(years.items(), key=lambda item: int(item[0]))),
        "by_subject": dict(subjects),
    }
    (ROOT / "data" / "ocr_full_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 全量 OCR 存储状态",
        "",
        f"- 唯一试卷：{len(records)} 套",
        f"- 已完成：{statuses['done']} 套",
        f"- 失败：{statuses['failed']} 套",
        f"- PDF：{pdf_count} 份",
        f"- Markdown：{md_count} 份",
        f"- 英语听力 MP3：{mp3_count} 份",
        f"- `papers/` 目录体积：{human_size(papers_size)}",
        "",
        "## 识别方式",
        "",
    ]
    for method, count in sorted(methods.items()):
        lines.append(f"- {method or '未记录'}：{count} 套")
    lines.extend(["", "## 按年份", "", "| 年份 | 已完成 |", "|---|---:|"])
    for year, count in sorted(years.items(), key=lambda item: int(item[0])):
        lines.append(f"| {year} | {count} |")
    lines.extend(["", "## 按科目", "", "| 科目 | 已完成 |", "|---|---:|"])
    for subject in ["语文", "数学", "英语", "物理", "化学", "生物", "政治", "历史", "地理"]:
        lines.append(f"| {subject} | {subjects.get(subject, 0)} |")
    lines.extend([
        "",
        "## 清单",
        "",
        "- `data/full_paper_manifest.csv`：全量唯一试卷的规范路径、OCR 方式和识别页数。",
        "- `data/ocr_full_summary.json`：机器可读的汇总统计。",
        "",
    ])
    (ROOT / "docs" / "storage-status.md").write_text("\n".join(lines), encoding="utf-8")

    papers_readme = "\n".join([
        "# 全量试卷文件",
        "",
        f"本目录保存 2008-2026 年九科唯一试卷，共 {len(records)} 套。",
        "",
        f"- 原卷 PDF：{pdf_count} 份",
        f"- OCR Markdown：{md_count} 份",
        f"- 英语听力 MP3：{mp3_count} 份",
        f"- `papers/` 目录体积：{human_size(papers_size)}",
        "",
        "## 存储结构",
        "",
        "```text",
        "papers/<年份>/<科目>/<地区或全国>/<卷型>/",
        "```",
        "",
        "常规科目使用 `PDF + md`；英语在有独立音频时使用 `PDF + md + mp3`。通用全国卷只保存一份，省份覆盖关系见 `data/coverage_matrix.csv`。",
        "",
        "## 老高考综合科目",
        "",
        "2016-2024 年老高考物理、化学、生物在卷型中保留“理综”，政治、历史、地理保留“文综”；实际正文按科目拆分保存。",
        "",
        "## 清单与统计",
        "",
        "- `data/full_paper_manifest.csv`",
        "- `data/ocr_full_summary.json`",
        "- `docs/storage-status.md`",
        "",
    ])
    (ROOT / "papers" / "README.md").write_text(papers_readme, encoding="utf-8")

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    start = readme.find("## 已入库试卷")
    end = readme.find("## 数据规模", start)
    if start >= 0 and end > start:
        block = "\n".join([
            "## 已入库试卷",
            "",
            f"- 唯一试卷：{len(records)} 套",
            f"- 原卷 PDF：{pdf_count} 份",
            f"- OCR Markdown：{md_count} 份",
            f"- 英语听力 MP3：{mp3_count} 份",
            f"- 文件体积：{human_size(papers_size)}",
            "- 全量清单：`data/full_paper_manifest.csv`",
            "- 存储状态：[docs/storage-status.md](docs/storage-status.md)",
            "",
        ])
        readme = readme[:start] + block + readme[end:]
    if "docs/storage-status.md" not in readme:
        readme = readme.replace("- [统一命名规范](docs/naming.md)", "- [全量 OCR 存储状态](docs/storage-status.md)\n- [统一命名规范](docs/naming.md)")
    readme_path.write_text(readme, encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if statuses["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
