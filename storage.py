"""ETF 份额数据的 Excel 存储。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from openpyxl import Workbook, load_workbook

from sse_client import EtfShare, validate_code, validate_date


DATA_DIR = Path("data")
STATUS_FILE = DATA_DIR / "_update_status.json"
HEADERS = [
    "日期",
    "ETF代码",
    "基金名称",
    "基金简称",
    "ETF类型",
    "总份额(万份)",
    "总份额(份)",
    "更新时间",
]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def etf_file_path(code: str) -> Path:
    return DATA_DIR / f"{validate_code(code)}.xlsx"


def load_share(code: str, stat_date: str) -> Optional[EtfShare]:
    """从本地 Excel 查询单只 ETF 指定日期记录。"""

    normalized_code = validate_code(code)
    normalized_date = validate_date(stat_date)
    records = _load_records(normalized_code)
    record = records.get(normalized_date)
    if not record:
        return None
    return _record_to_share(record)


def save_shares(shares: Iterable[EtfShare]) -> int:
    """批量保存 ETF 份额记录，同一代码同一日期以新数据覆盖旧数据。"""

    ensure_data_dir()
    grouped: Dict[str, List[EtfShare]] = {}
    for share in shares:
        grouped.setdefault(share.code, []).append(share)

    saved = 0
    for code, code_shares in grouped.items():
        records = _load_records(code)
        for share in code_shares:
            records[share.stat_date] = _share_to_record(share)
            saved += 1
        _write_records(code, records)
    return saved


def is_date_fully_updated(stat_date: str) -> bool:
    normalized_date = validate_date(stat_date)
    status = _load_status()
    return normalized_date in status.get("full_dates", {})


def mark_date_fully_updated(stat_date: str, record_count: int) -> None:
    ensure_data_dir()
    normalized_date = validate_date(stat_date)
    status = _load_status()
    status.setdefault("full_dates", {})[normalized_date] = {
        "record_count": record_count,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_records(code: str) -> Dict[str, Dict[str, object]]:
    ensure_data_dir()
    path = etf_file_path(code)
    if not path.exists():
        return {}

    workbook = load_workbook(path)
    sheet = workbook.active
    records: Dict[str, Dict[str, object]] = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        record = dict(zip(HEADERS, row))
        records[str(record["日期"])] = record
    return records


def _write_records(code: str, records: Dict[str, Dict[str, object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ETF份额"
    sheet.append(HEADERS)

    for stat_date in sorted(records):
        record = records[stat_date]
        sheet.append([record.get(header, "") for header in HEADERS])

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 28)

    workbook.save(etf_file_path(code))


def _share_to_record(share: EtfShare) -> Dict[str, object]:
    return {
        "日期": share.stat_date,
        "ETF代码": share.code,
        "基金名称": share.name,
        "基金简称": share.short_name,
        "ETF类型": share.etf_type,
        "总份额(万份)": share.total_volume_10k,
        "总份额(份)": share.total_volume_shares,
        "更新时间": datetime.now().isoformat(timespec="seconds"),
    }


def _record_to_share(record: Dict[str, object]) -> EtfShare:
    return EtfShare(
        stat_date=str(record.get("日期") or ""),
        code=str(record.get("ETF代码") or ""),
        name=str(record.get("基金名称") or ""),
        short_name=str(record.get("基金简称") or ""),
        etf_type=str(record.get("ETF类型") or ""),
        total_volume_10k=str(record.get("总份额(万份)") or ""),
        total_volume_shares=int(record.get("总份额(份)") or 0),
    )


def _load_status() -> Dict[str, object]:
    ensure_data_dir()
    if not STATUS_FILE.exists():
        return {"full_dates": {}}
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
