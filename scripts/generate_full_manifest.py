#!/usr/bin/env python3
"""生成不含本地来源路径的全量试卷清单。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ocr_all_papers import ROOT, build_records, load_rows

FIELDS = [
    "record_key", "status", "year", "subject", "area", "coverage_regions", "scope", "paper_type",
    "exam_mode", "comprehensive", "pdf_path", "md_path", "mp3_path", "ocr_method", "pages",
]


def parse_md(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", ""
    method = ""
    pages = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:20]:
        if line.startswith("ocr_method:"):
            method = line.split(":", 1)[1].strip()
        elif line.startswith("pages:"):
            pages = line.split(":", 1)[1].strip()
    return method, pages


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.exists() else ""


def main() -> int:
    records = build_records(load_rows(ROOT / "data" / "paper_inventory.csv"))
    output = ROOT / "data" / "full_paper_manifest.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        writer.writeheader()
        for record in records:
            pdf = Path(record["pdf_path"])
            md = Path(record["md_path"])
            mp3 = Path(record["mp3_path"])
            method, pages = parse_md(md)
            status = "done" if pdf.exists() and md.exists() else ("pdf_only" if pdf.exists() else "missing")
            writer.writerow({
                "record_key": record["key"],
                "status": status,
                "year": record["year"],
                "subject": record["subject"],
                "area": record["area"],
                "coverage_regions": record["coverage_regions"],
                "scope": record["scope"],
                "paper_type": record["paper_type"],
                "exam_mode": record["exam_mode"],
                "comprehensive": record["comprehensive"],
                "pdf_path": relative(pdf),
                "md_path": relative(md),
                "mp3_path": relative(mp3),
                "ocr_method": method,
                "pages": pages,
            })
    summary = {
        "records": len(records),
        "pdf": sum(1 for record in records if Path(record["pdf_path"]).exists()),
        "markdown": sum(1 for record in records if Path(record["md_path"]).exists()),
        "mp3": sum(1 for record in records if Path(record["mp3_path"]).exists()),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
