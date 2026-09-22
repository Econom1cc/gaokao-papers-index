#!/usr/bin/env python3
"""从覆盖矩阵和实际试卷文件重建仓库相对路径索引。"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from ocr_all_papers import ROOT, canonical_paper_type, infer_comprehensive, infer_exam_mode, load_coverage_types, load_rows

SUBJECT_SLUG = {
    "语文": "chinese", "数学": "math", "英语": "english", "物理": "physics", "化学": "chemistry",
    "生物": "biology", "政治": "politics", "历史": "history", "地理": "geography",
}
REGION_SLUG = {
    "北京": "beijing", "天津": "tianjin", "河北": "hebei", "山西": "shanxi", "内蒙古": "inner-mongolia",
    "辽宁": "liaoning", "吉林": "jilin", "黑龙江": "heilongjiang", "上海": "shanghai", "江苏": "jiangsu",
    "浙江": "zhejiang", "安徽": "anhui", "福建": "fujian", "江西": "jiangxi", "山东": "shandong",
    "河南": "henan", "湖北": "hubei", "湖南": "hunan", "广东": "guangdong", "广西": "guangxi",
    "海南": "hainan", "重庆": "chongqing", "四川": "sichuan", "贵州": "guizhou", "云南": "yunnan",
    "西藏": "tibet", "陕西": "shaanxi", "甘肃": "gansu", "青海": "qinghai", "宁夏": "ningxia",
    "新疆": "xinjiang",
}
REFORM_START = {
    "浙江": 2017, "上海": 2017, "北京": 2020, "天津": 2020, "山东": 2020, "海南": 2020,
    "河北": 2021, "辽宁": 2021, "江苏": 2021, "福建": 2021, "湖北": 2021, "湖南": 2021,
    "广东": 2021, "重庆": 2021, "江西": 2024, "甘肃": 2024, "黑龙江": 2024, "吉林": 2024,
    "安徽": 2024, "贵州": 2024, "广西": 2024, "山西": 2025, "河南": 2025, "陕西": 2025,
    "内蒙古": 2025, "四川": 2025, "云南": 2025, "宁夏": 2025, "青海": 2025,
}
FIELDS = [
    "年份", "科目", "地区", "高考模式", "改革起始年", "卷别性质", "范围", "卷型",
    "状态", "试卷路径", "Markdown路径", "听力路径", "OCR方式", "识别页数",
]


def relative_path(target: Path | str, from_dir: Path) -> str:
    if target is None or not str(target).strip():
        return ""
    path = Path(target)
    if not path.exists() or not path.is_file():
        return ""
    return os.path.relpath(path, from_dir).replace(os.sep, "/")


def relative_link(target: Path | str, from_dir: Path, label: str) -> str:
    relative = relative_path(target, from_dir)
    return f"[{label}]({relative})" if relative else ""


def record_key(row: dict[str, str], coverage_type: str) -> str:
    file_type = canonical_paper_type(row["年份"], coverage_type)
    area = "全国" if row["范围"] == "common" or "全国" in file_type else row["地区"]
    return "|".join((row["年份"], row["科目"], area, file_type))


def load_record_map():
    rows = load_rows(ROOT / "data" / "paper_inventory.csv")
    coverage = load_coverage_types()
    result = {}
    for row in rows:
        if row.get("status") != "original" or row.get("ext", "").lower() != ".pdf":
            continue
        coverage_type = coverage.get((row["year"], row["subject"], row["region"]), row["paper_type"])
        key = record_key({
            "年份": row["year"], "科目": row["subject"], "地区": row["region"],
            "范围": "common" if "全国" in canonical_paper_type(row["year"], coverage_type) or row["scope"] == "common" else "local",
        }, coverage_type)
        existing = result.get(key)
        if existing is None:
            result[key] = row
    return result


def build_rows() -> list[dict[str, str]]:
    coverage_path = ROOT / "data" / "coverage_matrix.csv"
    coverage_rows = list(csv.DictReader(coverage_path.open(encoding="utf-8-sig", newline="")))
    record_map = load_record_map()
    import ocr_all_papers as ocr
    built_records = {str(item["key"]): item for item in ocr.build_records(load_rows(ROOT / "data" / "paper_inventory.csv"))}
    built = []
    for source in coverage_rows:
        file_type_raw = source.get("卷型") or ""
        file_type = canonical_paper_type(source["年份"], file_type_raw) if file_type_raw else ""
        source_key = record_key(source, file_type_raw) if file_type_raw else ""
        chosen = record_map.get(source_key)
        year = source["年份"]
        subject = source["科目"]
        region = source["地区"]
        area = "全国" if source["范围"] == "common" or "全国" in file_type else region
        exam_mode = infer_exam_mode(year, area, region, file_type, Path(chosen["source_path"]).name if chosen else "")
        start = REFORM_START.get(area, REFORM_START.get(region, ""))
        record = None
        if chosen:
            record = built_records.get(source_key)
        if record:
            pdf_path = Path(record["pdf_path"])
            md_path = Path(record["md_path"])
            mp3_path = Path(record["mp3_path"])
            status = "done" if pdf_path.exists() and md_path.exists() else ("pdf_only" if pdf_path.exists() else "missing")
            method = "pypdf" if md_path.exists() and "ocr_method: pypdf" in md_path.read_text(encoding="utf-8", errors="ignore")[:1000] else ("rapidocr" if md_path.exists() else "")
            pages = ""
            if md_path.exists():
                for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:20]:
                    if line.startswith("pages:"):
                        pages = line.split(":", 1)[1].strip()
                        break
        else:
            pdf_path = md_path = mp3_path = None
            status = "missing"
            method = ""
            pages = ""
        # 链接相对于每个输出文件的位置稍后重写。
        built.append({
            "年份": year, "科目": subject, "地区": region,
            "高考模式": exam_mode, "改革起始年": str(start) if start else "",
            "卷别性质": "全国卷" if source["范围"] == "common" else ("地方/区域卷" if source["范围"] != "missing" else ""),
            "范围": source["范围"], "卷型": file_type or file_type_raw,
            "状态": status,
            "_pdf": str(pdf_path) if pdf_path else "",
            "_md": str(md_path) if md_path else "",
            "_mp3": str(mp3_path) if mp3_path else "",
            "OCR方式": method, "识别页数": pages,
        })
    return built


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in FIELDS}
            output["试卷路径"] = relative_path(Path(row["_pdf"]), path.parent)
            output["Markdown路径"] = relative_path(Path(row["_md"]), path.parent)
            output["听力路径"] = relative_path(Path(row["_mp3"]), path.parent)
            writer.writerow(output)


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def write_markdown_index(path: Path, rows: list[dict[str, str]], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status_label = {"done": "完整", "pdf_only": "待OCR", "missing": "缺失"}
    lines = [
        f"# {title}",
        "",
        f"> 共 {len(rows)} 条覆盖记录。点击“试卷”“OCR”“听力”进入仓库文件。",
        "",
        "| 年份 | 科目 | 地区 | 高考模式 | 卷型 | 状态 | 试卷 | OCR | 听力 | 识别方式 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join([
            markdown_cell(row["年份"]),
            markdown_cell(row["科目"]),
            markdown_cell(row["地区"]),
            markdown_cell(row["高考模式"]),
            markdown_cell(row["卷型"]),
            markdown_cell(status_label.get(row["状态"], row["状态"])),
            relative_link(Path(row["_pdf"]), path.parent, "PDF") or "-",
            relative_link(Path(row["_md"]), path.parent, "Markdown") or "-",
            relative_link(Path(row["_mp3"]), path.parent, "MP3") or "-",
            markdown_cell(row["OCR方式"]) or "-",
        ]) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows = build_rows()
    rows.sort(key=lambda row: (
        int(row["年份"]), list(SUBJECT_SLUG).index(row["科目"]), list(REGION_SLUG).index(row["地区"])
    ))

    write_csv(ROOT / "indexes" / "catalog.csv", rows)
    write_markdown_index(ROOT / "indexes" / "catalog.md", rows, "2008-2026 全国高考试卷总索引")

    partitions = [
        ("科目", SUBJECT_SLUG, ROOT / "indexes" / "by-subject"),
        ("地区", REGION_SLUG, ROOT / "indexes" / "by-region"),
    ]
    for field, mapping, directory in partitions:
        for key, slug in mapping.items():
            part = [row for row in rows if row[field] == key]
            write_csv(directory / f"{slug}.csv", part)
            write_markdown_index(directory / f"{slug}.md", part, f"{key}高考试卷索引")
    for year in range(2008, 2027):
        part = [row for row in rows if row["年份"] == str(year)]
        write_csv(ROOT / "indexes" / "by-year" / f"{year}.csv", part)
        write_markdown_index(ROOT / "indexes" / "by-year" / f"{year}.md", part, f"{year} 年高考试卷索引")
    for mode, slug in [("老高考", "old-gaokao"), ("新高考", "new-gaokao")]:
        part = [row for row in rows if row["高考模式"] == mode]
        write_csv(ROOT / "indexes" / "by-exam-system" / f"{slug}.csv", part)
        write_markdown_index(ROOT / "indexes" / "by-exam-system" / f"{slug}.md", part, f"{mode}试卷索引")

    json_rows = []
    for row in rows:
        item = {field: row.get(field, "") for field in FIELDS}
        item["试卷路径"] = relative_path(Path(row["_pdf"]), ROOT)
        item["Markdown路径"] = relative_path(Path(row["_md"]), ROOT)
        item["听力路径"] = relative_path(Path(row["_mp3"]), ROOT)
        json_rows.append(item)
    (ROOT / "indexes" / "catalog.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in json_rows) + "\n", encoding="utf-8"
    )
    hierarchy = {"by_subject": {}, "by_region": {}, "by_year": {}, "by_exam_system": {}}
    for row in json_rows:
        hierarchy["by_subject"].setdefault(row["科目"], {}).setdefault(row["年份"], []).append(row)
        hierarchy["by_region"].setdefault(row["地区"], {}).setdefault(row["年份"], []).append(row)
        hierarchy["by_year"].setdefault(row["年份"], {}).setdefault(row["科目"], {}).setdefault(row["地区"], []).append(row)
        hierarchy["by_exam_system"].setdefault(row["高考模式"], {}).setdefault(row["年份"], []).append(row)
    (ROOT / "indexes" / "hierarchy.json").write_text(
        json.dumps(hierarchy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    navigation = [
        "# 高考索引导航", "",
        "Markdown 索引可以直接点击进入试卷、OCR Markdown 和听力文件；CSV 作为数据导出，不再承载链接语法。", "",
        "## 可点击索引", "",
        "- [完整总索引](catalog.md)", "",
        "### 按科目", "",
    ]
    for subject, slug in SUBJECT_SLUG.items():
        navigation.append(f"- [{subject}](by-subject/{slug}.md)")
    navigation.extend(["", "### 按地区", ""])
    for region, slug in REGION_SLUG.items():
        navigation.append(f"- [{region}](by-region/{slug}.md)")
    navigation.extend(["", "### 按年份", ""])
    for year in range(2008, 2027):
        navigation.append(f"- [{year}](by-year/{year}.md)")
    navigation.extend([
        "", "### 按新老高考", "",
        "- [老高考](by-exam-system/old-gaokao.md)",
        "- [新高考](by-exam-system/new-gaokao.md)",
        "", "## 数据导出", "",
        "- [完整 CSV](catalog.csv)",
        "- [JSON Lines](catalog.jsonl)",
        "- [层级 JSON](hierarchy.json)",
        "",
    ])
    (ROOT / "indexes" / "README.md").write_text("\n".join(navigation), encoding="utf-8")

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    start = readme.find("## 索引入口")
    end = readme.find("## 目录规范", start)
    if start >= 0 and end > start:
        readme = readme[:start] + "## 索引入口\n\n- [可点击索引总导航](indexes/README.md)\n\n" + readme[end:]
    readme_path.write_text(readme, encoding="utf-8")
    print(json.dumps({"rows": len(rows), "done": sum(row["状态"] == "done" for row in rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
