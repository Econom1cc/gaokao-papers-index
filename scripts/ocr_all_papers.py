#!/usr/bin/env python3
"""按覆盖清单选择唯一试卷，生成 PDF + Markdown OCR，并维护可续跑清单。"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

logging.disable(logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "data" / "paper_inventory.csv"
DEFAULT_MANIFEST = ROOT / "data" / "full_paper_manifest.csv"
DEFAULT_PROGRESS = ROOT / ".ocr-progress.json"
SUBJECT_ORDER = ["语文", "数学", "英语", "物理", "化学", "生物", "政治", "历史", "地理"]
SCIENCE = {"物理", "化学", "生物"}
HUMANITIES = {"政治", "历史", "地理"}
REFORM_START = {
    "浙江": 2017, "上海": 2017, "北京": 2020, "天津": 2020, "山东": 2020, "海南": 2020,
    "河北": 2021, "辽宁": 2021, "江苏": 2021, "福建": 2021, "湖北": 2021, "湖南": 2021,
    "广东": 2021, "重庆": 2021, "江西": 2024, "甘肃": 2024, "黑龙江": 2024, "吉林": 2024,
    "安徽": 2024, "贵州": 2024, "广西": 2024, "山西": 2025, "河南": 2025, "陕西": 2025,
    "内蒙古": 2025, "四川": 2025, "云南": 2025, "宁夏": 2025, "青海": 2025,
}
MANIFEST_FIELDS = [
    "status", "year", "subject", "area", "coverage_regions", "scope", "paper_type",
    "exam_mode", "comprehensive", "ocr_method", "pages", "pdf_path", "md_path",
    "mp3_path", "source_filename", "source_group", "note",
]


def clean_component(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip().strip(".")
    return re.sub(r"\s+", " ", value) or "未命名"


def source_score(row: dict[str, str]) -> tuple[int, int, int]:
    name = Path(row["source_path"]).name
    return (
        0 if ("空白卷" in name or "原卷" in name) else 1,
        1 if ("解析" in name or "答案" in name) else 0,
        len(name),
    )


def infer_exam_mode(year: str, area: str, region: str, paper_type: str, source_filename: str) -> str:
    label = f"{paper_type} {source_filename}"
    if int(year) >= 2021 and (
        "新高考" in label or paper_type in {"全国I卷", "全国II卷", "全国Ⅰ卷", "全国Ⅱ卷"}
    ):
        return "新高考"
    start = REFORM_START.get(area, REFORM_START.get(region, 9999))
    return "新高考" if int(year) >= start else "老高考"


def normalize_paper_type(paper_type: str, subject: str, exam_mode: str) -> str:
    value = paper_type.replace("III", "Ⅲ").replace("II", "Ⅱ").replace("I", "Ⅰ")
    if exam_mode == "老高考" and subject in SCIENCE and "理综" not in value:
        if value.endswith("卷") and not re.search(r"[ⅠⅡⅢ甲乙丙丁0-9]", value):
            value = value[:-1] + "理综"
        else:
            value += "理综"
    if exam_mode == "老高考" and subject in HUMANITIES and "文综" not in value:
        if value.endswith("卷") and not re.search(r"[ⅠⅡⅢ甲乙丙丁0-9]", value):
            value = value[:-1] + "文综"
        else:
            value += "文综"
    return value


def canonical_paper_type(year: str, paper_type: str) -> str:
    value = paper_type.replace("III", "Ⅲ").replace("II", "Ⅱ").replace("I", "Ⅰ")
    new_match = re.fullmatch(r"新高考(?:全国)?([ⅠⅡ])卷", value)
    if new_match:
        return f"新高考全国{new_match.group(1)}卷"
    match = re.fullmatch(r"(?:新高考|新课标)?全国([ⅠⅡ])卷", value)
    if not match:
        return value
    numeral = match.group(1)
    if int(year) >= 2021:
        return f"新高考全国{numeral}卷"
    if int(year) >= 2014:
        return f"新课标全国{numeral}卷"
    return f"全国{numeral}卷"


def infer_comprehensive(subject: str, exam_mode: str) -> str:
    if exam_mode == "老高考" and subject in SCIENCE:
        return "理综"
    if exam_mode == "老高考" and subject in HUMANITIES:
        return "文综"
    return "无"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def load_coverage_types() -> dict[tuple[str, str, str], str]:
    path = ROOT / "data" / "coverage_matrix.csv"
    result: dict[tuple[str, str, str], str] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            if row.get("卷型"):
                result[(row["年份"], row["科目"], row["地区"])] = row["卷型"]
    return result


def build_records(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    coverage_types = load_coverage_types()
    canonical: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    audio_candidates: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)

    def normalized_type(row: dict[str, str]) -> str:
        source_type = coverage_types.get((row["year"], row["subject"], row["region"]), row["paper_type"])
        return canonical_paper_type(row["year"], source_type)

    def normalized_area(row: dict[str, str], file_type: str) -> str:
        return "全国" if row["scope"] == "common" or "全国" in file_type else row["region"]

    for row in rows:
        if row.get("subject") == "英语" and row.get("ext", "").lower() == ".mp3":
            if not Path(row.get("source_path", "")).exists():
                continue
            file_type = normalized_type(row)
            area = normalized_area(row, file_type)
            audio_candidates[(row["year"], row["subject"], area, file_type)].append(row)
            continue
        if row.get("status") != "original" or row.get("ext", "").lower() != ".pdf":
            continue
        if not Path(row.get("source_path", "")).exists():
            continue
        file_type = normalized_type(row)
        area = normalized_area(row, file_type)
        canonical[(row["year"], row["subject"], area, file_type)].append(row)

    records: list[dict[str, object]] = []
    for key, items in canonical.items():
        row = min(items, key=source_score)
        year, subject, area, file_type = key
        exam_mode = infer_exam_mode(year, area, row["region"], file_type, Path(row["source_path"]).name)
        comprehensive = infer_comprehensive(subject, exam_mode)
        display_paper_type = normalize_paper_type(file_type, subject, exam_mode)
        audios = audio_candidates.get(key, [])
        audio = min(audios, key=lambda item: (len(Path(item["source_path"]).name), item["source_path"])) if audios else None

        label = display_paper_type
        if area != "全国" and area not in label and label not in area:
            label = f"{area}{label}"
        stem = f"{year}_{subject}_{label}"
        outdir = ROOT / "papers" / year / subject / clean_component(area) / clean_component(display_paper_type)
        records.append({
            "key": "|".join(key),
            "year": year,
            "subject": subject,
            "area": area,
            "coverage_regions": row["region"],
            "scope": "common" if area == "全国" else row["scope"],
            "paper_type": display_paper_type,
            "source_paper_type": row["paper_type"],
            "exam_mode": exam_mode,
            "comprehensive": comprehensive,
            "source_path": row["source_path"],
            "source_filename": Path(row["source_path"]).name,
            "source_group": row.get("source_group", ""),
            "audio_path": audio["source_path"] if audio else "",
            "pdf_path": outdir / f"{stem}_原卷.pdf",
            "md_path": outdir / f"{stem}_OCR与考点.md",
            "mp3_path": outdir / f"{stem}_听力.mp3",
            "status": "pending",
            "ocr_method": "",
            "pages": 0,
            "note": "",
        })
    records.sort(key=lambda record: (
        -int(record["year"]), SUBJECT_ORDER.index(str(record["subject"])), str(record["area"]), str(record["paper_type"])
    ))
    return records


def extract_native_pdf(pdf: Path) -> list[dict[str, object]] | None:
    reader = PdfReader(str(pdf), strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    native: list[str] = []
    for page in reader.pages:
        try:
            native.append((page.extract_text() or "").strip())
        except Exception:
            native.append("")
    total = sum(len(text) for text in native)
    if total >= max(500, len(reader.pages) * 80):
        return [{"page": i + 1, "text": text} for i, text in enumerate(native)]
    return None


def extract_pdf(pdf: Path, engine_holder: list[object | None]) -> tuple[list[dict[str, object]], str]:
    native_pages = extract_native_pdf(pdf)
    if native_pages is not None:
        return native_pages, "pypdf"

    if engine_holder[0] is None:
        dml_pkgs = os.environ.get("CODEX_DML_PKGS")
        if dml_pkgs and Path(dml_pkgs).exists():
            sys.path.insert(0, dml_pkgs)
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            extra = os.environ.get("CODEX_OCR_PKGS")
            if extra:
                sys.path.insert(0, extra)
            if dml_pkgs and Path(dml_pkgs).exists():
                sys.path.insert(0, dml_pkgs)
            from rapidocr_onnxruntime import RapidOCR
        threads = max(1, int(os.environ.get("OCR_INTRA_THREADS", "1")))
        det_side = max(480, int(os.environ.get("OCR_DET_SIDE", "736")))
        rec_batch = max(1, int(os.environ.get("OCR_REC_BATCH", "6")))
        use_dml = os.environ.get("OCR_USE_DML", "").lower() in {"1", "true", "yes"}
        engine_holder[0] = RapidOCR(
            intra_op_num_threads=threads,
            inter_op_num_threads=1,
            use_cls=False,
            det_limit_side_len=det_side,
            rec_batch_num=rec_batch,
            det_use_dml=use_dml,
            rec_use_dml=use_dml,
        )
        if os.environ.get("OCR_DEBUG_PROVIDERS") == "1":
            det_providers = engine_holder[0].text_det.infer.session.get_providers()
            rec_providers = engine_holder[0].text_rec.session.session.get_providers()
            print(f"OCR_PROVIDERS det={det_providers} rec={rec_providers}", flush=True)
    from pdf2image import convert_from_path
    import numpy as np

    dpi = max(96, int(os.environ.get("OCR_DPI", "120")))
    images = convert_from_path(str(pdf), dpi=dpi, fmt="jpeg")
    pages: list[dict[str, object]] = []
    for index, image in enumerate(images):
        result, _ = engine_holder[0](np.array(image))
        text = "\n".join(item[1] for item in (result or []))
        pages.append({"page": index + 1, "text": text.strip()})
    return pages, "rapidocr"


def render_markdown(record: dict[str, object], pages: list[dict[str, object]], method: str) -> str:
    lines = [
        "---",
        f"year: {record['year']}",
        f"region: {record['area']}",
        f"subject: {record['subject']}",
        f"area: {record['area']}",
        f"paper_type: {record['paper_type']}",
        f"scope: {record['scope']}",
        f"exam_mode: {record['exam_mode']}",
        f"comprehensive: {record['comprehensive']}",
        f"ocr_method: {method}",
        f"pages: {len(pages)}",
        f"source_file: \"{record['source_filename']}\"",
        "---",
        "",
        f"# {record['year']}年{record['area']}高考{record['subject']}试卷",
        "",
        "## 文件信息",
        "",
        f"- 原卷 PDF：`{Path(record['pdf_path']).name}`",
        f"- 地区或卷区：{record['area']}",
        f"- 卷型：{record['paper_type']}",
        f"- 覆盖范围：{'通用全国卷' if record['scope'] == 'common' else '地方/区域卷'}",
        f"- 考试模式：{record['exam_mode']}",
        f"- 综合科目：{record['comprehensive']}",
        f"- 存储格式：PDF + md" + (" + mp3（英语听力）" if record["subject"] == "英语" and record.get("audio_path") else ""),
        "",
    ]
    if record["comprehensive"] != "无":
        lines.extend([
            f"> 老高考综合科目在原卷中属于{record['comprehensive']}；本文件是按{record['subject']}拆分保存的识别文本。",
            "",
        ])
    lines.extend(["## OCR 正文", ""])
    for page in pages:
        lines.extend([f"### 第 {page['page']} 页", "", page["text"] or "本页未识别出可用文本。", ""])
    return "\n".join(lines).rstrip() + "\n"


def load_progress(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(row["key"]): row for row in rows if isinstance(row, dict) and row.get("key")}


def save_progress(path: Path, progress: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(progress.values()), ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(path: Path, records: list[dict[str, object]], progress: dict[str, dict[str, object]]) -> None:
    old: dict[str, dict[str, str]] = {}
    if path.exists():
        try:
            with path.open(encoding="utf-8-sig", newline="") as fp:
                old = {row["record_key"]: row for row in csv.DictReader(fp) if row.get("record_key")}
        except (OSError, KeyError):
            old = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        fields = ["record_key"] + MANIFEST_FIELDS
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for record in records:
            key = str(record["key"])
            row = {
                "record_key": key,
                "status": record["status"],
                "year": record["year"],
                "subject": record["subject"],
                "area": record["area"],
                "coverage_regions": record["coverage_regions"],
                "scope": record["scope"],
                "paper_type": record["paper_type"],
                "exam_mode": record["exam_mode"],
                "comprehensive": record["comprehensive"],
                "ocr_method": record["ocr_method"],
                "pages": record["pages"],
                "pdf_path": "",
                "md_path": "",
                "mp3_path": "",
                "source_filename": record["source_filename"],
                "source_group": record["source_group"],
                "note": record["note"],
            }
            status = progress.get(key)
            if status:
                for field in MANIFEST_FIELDS:
                    if field in status:
                        row[field] = status[field]
            elif key in old:
                for field in MANIFEST_FIELDS:
                    row[field] = old[key].get(field, "")
            for field in ["pdf_path", "md_path", "mp3_path"]:
                if row[field]:
                    try:
                        row[field] = str(Path(row[field]).relative_to(ROOT)).replace(os.sep, "/")
                    except ValueError:
                        pass
            writer.writerow(row)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--year", action="append", type=int, default=[])
    parser.add_argument("--subject", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--text-only", action="store_true", help="只处理可提取文本层的 PDF")
    parser.add_argument("--scanned-only", action="store_true", help="只处理需要 OCR 的扫描 PDF")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = build_records(load_rows(args.inventory))
    if args.year:
        years = set(args.year)
        records = [r for r in records if int(r["year"]) in years]
    if args.subject:
        subjects = set(args.subject)
        records = [r for r in records if r["subject"] in subjects]
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("--shard-index 必须位于 0 到 --shard-count-1 之间")
    if args.shard_count > 1:
        records = [r for i, r in enumerate(records) if i % args.shard_count == args.shard_index]

    progress = load_progress(args.progress)
    engine_holder: list[object | None] = [None]
    processed = 0
    failed = 0
    total_changed = 0

    for index, record in enumerate(records, 1):
        key = str(record["key"])
        previous = progress.get(key, {})
        pdf = Path(record["pdf_path"])
        md = Path(record["md_path"])
        mp3 = Path(record["mp3_path"])

        if not args.force and previous.get("status") == "done" and pdf.exists() and md.exists():
            processed += 1
            continue
        if not args.force and pdf.exists() and md.exists():
            progress[key] = {
                "key": key, "status": "done", "year": record["year"], "subject": record["subject"],
                "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "existing",
                "pages": 0, "pdf_path": str(pdf), "md_path": str(md),
                "mp3_path": str(mp3) if mp3.exists() else "", "note": "已有文件，跳过重建",
            }
            save_progress(args.progress, progress)
            processed += 1
            continue

        started = time.time()
        try:
            pdf.parent.mkdir(parents=True, exist_ok=True)
            if not pdf.exists() or args.force:
                shutil.copy2(record["source_path"], pdf)
            if args.text_only:
                native_pages = extract_native_pdf(pdf)
                if native_pages is None:
                    progress[key] = {
                        "key": key, "status": "needs_ocr", "year": record["year"], "subject": record["subject"],
                        "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "",
                        "pages": 0, "pdf_path": str(pdf), "md_path": str(md), "mp3_path": "",
                        "note": "文本层不足，等待扫描件阶段",
                    }
                    save_progress(args.progress, progress)
                    continue
                pages, method = native_pages, "pypdf"
            elif args.scanned_only:
                native_pages = extract_native_pdf(pdf)
                if native_pages is not None:
                    progress[key] = {
                        "key": key, "status": "native_complete", "year": record["year"], "subject": record["subject"],
                        "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "pypdf",
                        "pages": len(native_pages), "pdf_path": str(pdf), "md_path": str(md), "mp3_path": "",
                        "note": "文本层已由前一阶段完成",
                    }
                    save_progress(args.progress, progress)
                    continue
                pages, method = extract_pdf(pdf, engine_holder)
            else:
                pages, method = extract_pdf(pdf, engine_holder)
            md.write_text(render_markdown(record, pages, method), encoding="utf-8")
            audio_path = str(record.get("audio_path") or "")
            if audio_path and Path(audio_path).exists():
                shutil.copy2(audio_path, mp3)
            elif mp3.exists() and not args.force:
                pass
            else:
                mp3 = Path("")
            progress[key] = {
                "key": key, "status": "done", "year": record["year"], "subject": record["subject"],
                "area": record["area"], "paper_type": record["paper_type"], "ocr_method": method,
                "pages": len(pages), "pdf_path": str(Path(record["pdf_path"])),
                "md_path": str(Path(record["md_path"])), "mp3_path": str(Path(record["mp3_path"])) if record.get("audio_path") and Path(str(record["audio_path"])).exists() else "",
                "note": "",
            }
            processed += 1
            total_changed += 1
        except Exception as exc:
            failed += 1
            progress[key] = {
                "key": key, "status": "failed", "year": record["year"], "subject": record["subject"],
                "area": record["area"], "paper_type": record["paper_type"], "ocr_method": "",
                "pages": 0, "pdf_path": str(pdf), "md_path": str(md), "mp3_path": "",
                "note": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
        save_progress(args.progress, progress)
        elapsed = time.time() - started
        if total_changed <= 10 or total_changed % 5 == 0 or failed:
            state = progress[key]["status"]
            print(f"[{index}/{len(records)}] {record['year']} {record['subject']} {record['area']} {record['paper_type']} | {state} | {progress[key].get('ocr_method','')} | {elapsed:.1f}s", flush=True)
        if args.limit and total_changed >= args.limit:
            break

    write_manifest(args.manifest, build_records(load_rows(args.inventory)), progress)
    stats = defaultdict(int)
    for item in progress.values():
        stats[str(item.get("status", "unknown"))] += 1
    print(json.dumps({"requested": len(records), "processed": processed, "changed": total_changed, "failed": failed, "progress": dict(stats)}, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
