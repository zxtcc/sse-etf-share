"""ETF 份额数据的 Excel 存储。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Dict, Iterable, List, Optional

from openpyxl import Workbook, load_workbook

from sse_client import EtfShare, validate_code, validate_date


DATA_DIR = Path(__file__).resolve().parent / "data"
STATUS_FILE = DATA_DIR / "_update_status.json"
CATALOG_FILENAME = "_fund_catalog.json"
FAVORITES_FILENAME = "_favorites.json"
_catalog_lock = Lock()
_favorites_lock = Lock()
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
    names = {}
    for code, code_shares in grouped.items():
        records = _load_records(code)
        for share in code_shares:
            records[share.stat_date] = _share_to_record(share)
            saved += 1
        _write_records(code, records)
        for day in sorted(records, reverse=True):
            record = records[day]
            name = str(record.get("基金名称") or record.get("基金简称") or "").strip()
            if name:
                names[code] = name
                break
    if names:
        _save_catalog_names(names)
    return saved


def local_codes() -> List[str]:
    """列出本地 ETF 工作簿的代码。"""
    return sorted(
        path.stem for path in DATA_DIR.glob("[0-9]" * 6 + ".xlsx")
        if path.is_file()
    )


def local_funds(codes: List[str]) -> List[Dict[str, str]]:
    names = _load_catalog_names()
    return [{"code": code, "name": names.get(code, "")} for code in codes]


def _load_catalog_names() -> Dict[str, str]:
    return _read_name_map(CATALOG_FILENAME)


def _read_name_map(filename: str) -> Dict[str, str]:
    try:
        return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _save_catalog_names(updates: Dict[str, str]) -> None:
    with _catalog_lock:
        names = _load_catalog_names()
        if all(names.get(code) == name for code, name in updates.items()):
            return
        names.update(updates)
        _write_name_map(CATALOG_FILENAME, names)


def _write_name_map(filename: str, names: Dict[str, str]) -> None:
    ensure_data_dir()
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA_DIR, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(names, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.close()
            temporary.replace(DATA_DIR / filename)
        finally:
            temporary.unlink(missing_ok=True)


def load_favorites() -> Dict[str, str]:
    return _read_name_map(FAVORITES_FILENAME)


def set_favorite(code: str, enabled: bool) -> Dict[str, str]:
    with _favorites_lock:
        favorites = load_favorites()
        if enabled:
            if not etf_file_path(code).is_file():
                raise FileNotFoundError(code)
            favorites[code] = _load_catalog_names().get(code) or favorites.get(code, "")
        else:
            favorites.pop(code, None)
        _write_name_map(FAVORITES_FILENAME, favorites)
        return favorites


def load_history(code: str, start: str, end: str) -> List[Dict[str, object]]:
    """按日期升序返回份额，以及相对上一条本地记录的变化。"""
    records = _load_records(code)
    history = []
    previous = None
    for stat_date in sorted(records):
        if stat_date > end:
            break
        share = _record_to_share(records[stat_date])
        if stat_date >= start:
            change = None if previous is None else share.total_volume_shares - previous
            history.append({**share.to_dict(), "change_shares": change})
        previous = share.total_volume_shares
    return history


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
