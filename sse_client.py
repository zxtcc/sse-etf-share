"""上海交易所 ETF 份额查询客户端。"""

from __future__ import annotations

import re
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from random import uniform
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", module="urllib3")

import requests


SSE_QUERY_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_EXPAND_NAME_URL = "https://query.sse.com.cn/security/stock/queryExpandName.do"
SSE_REFERER = "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/"
ETF_SCALE_SQL_ID = "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"


class SseClientError(RuntimeError):
    """上交所接口调用或解析失败。"""


@dataclass(frozen=True)
class EtfShare:
    """单只 ETF 在指定日期的份额信息。"""

    stat_date: str
    code: str
    name: str
    short_name: str
    etf_type: str
    total_volume_10k: str
    total_volume_shares: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stat_date": self.stat_date,
            "code": self.code,
            "name": self.name,
            "short_name": self.short_name,
            "etf_type": self.etf_type,
            "total_volume_10k": self.total_volume_10k,
            "total_volume_shares": self.total_volume_shares,
        }


class SseEtfClient:
    """封装上交所 ETF 规模页面使用的数据接口。"""

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": SSE_REFERER,
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
            }
        )

    def fetch_share(self, code: str, stat_date: str) -> Optional[EtfShare]:
        """查询指定 ETF 在指定日期的份额；无匹配数据时返回 None。"""

        normalized_code = validate_code(code)
        normalized_date = validate_date(stat_date)
        rows = self.fetch_rows_for_date(normalized_date, page_size=10000)
        matched = next(
            (
                row
                for row in rows
                if str(row.get("SEC_CODE", "")).strip() == normalized_code
            ),
            None,
        )
        if not matched:
            return None

        short_name = str(matched.get("SEC_NAME") or "").strip()
        expanded_name = self._fetch_expand_name(normalized_code) or short_name
        volume_10k = normalize_decimal(matched.get("TOT_VOL"))
        shares = int((Decimal(volume_10k) * Decimal("10000")).to_integral_value())

        return EtfShare(
            stat_date=str(matched.get("STAT_DATE") or normalized_date),
            code=normalized_code,
            name=expanded_name,
            short_name=short_name,
            etf_type=str(matched.get("ETF_TYPE") or ""),
            total_volume_10k=volume_10k,
            total_volume_shares=shares,
        )

    def fetch_all_shares_for_date(
        self,
        stat_date: str,
        page_size: int = 1000,
        pause_range: Optional[Tuple[float, float]] = None,
    ) -> List[EtfShare]:
        """分页查询指定日期的全部 ETF 份额数据。"""

        normalized_date = validate_date(stat_date)
        rows = self.fetch_rows_for_date(
            normalized_date,
            page_size=page_size,
            pause_range=pause_range,
        )
        return [share_from_row(row, normalized_date) for row in rows]

    def fetch_rows_for_date(
        self,
        stat_date: str,
        page_size: int = 1000,
        pause_range: Optional[Tuple[float, float]] = None,
    ) -> List[Dict[str, Any]]:
        """按日期分页获取 ETF 规模原始列表。"""

        normalized_date = validate_date(stat_date)
        page_no = 1
        page_count = 1
        rows: List[Dict[str, Any]] = []

        while page_no <= page_count:
            payload = self._fetch_page(normalized_date, page_no, page_size)
            page_rows = extract_rows(payload)
            rows.extend(page_rows)

            page_help = payload.get("pageHelp") or {}
            page_count = int(page_help.get("pageCount") or 1)
            if pause_range:
                time.sleep(uniform(*pause_range))
            page_no += 1

        return rows

    def _fetch_page(
        self,
        stat_date: str,
        page_no: int,
        page_size: int,
    ) -> Dict[str, Any]:
        params = {
            "isPagination": "true",
            "pageHelp.pageSize": str(page_size),
            "pageHelp.pageNo": str(page_no),
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": str(page_no),
            "sqlId": ETF_SCALE_SQL_ID,
            "STAT_DATE": stat_date,
        }
        return self._get_json(SSE_QUERY_URL, params)

    def _fetch_expand_name(self, code: str) -> str:
        params = {"secCodes": code}
        payload = self._get_json(SSE_EXPAND_NAME_URL, params)
        result = payload.get("result")
        if not isinstance(result, list) or not result:
            return ""

        first = result[0]
        if isinstance(first, list) and len(first) >= 2:
            return str(first[1]).strip()
        return ""

    def _get_json(self, url: str, params: Dict[str, str]) -> Dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise SseClientError(f"访问上交所接口失败：{exc}") from exc
        except ValueError as exc:
            raise SseClientError("上交所接口没有返回有效 JSON") from exc


def validate_code(code: str) -> str:
    normalized = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", normalized):
        raise ValueError("ETF 代码必须是 6 位数字")
    return normalized


def validate_date(stat_date: str) -> str:
    normalized = str(stat_date or "").strip()
    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("日期格式必须是 YYYY-MM-DD") from exc
    return parsed.strftime("%Y-%m-%d")


def normalize_decimal(value: Any) -> str:
    text = str(value or "").replace(",", "").strip()
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise SseClientError(f"份额字段无法解析：{value}") from exc
    return format(number.normalize(), "f")


def extract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, list):
        return result

    page_data = payload.get("pageHelp", {}).get("data")
    if isinstance(page_data, list):
        return page_data

    raise SseClientError("上交所返回的数据格式不符合预期")


def share_from_row(row: Dict[str, Any], fallback_date: str) -> EtfShare:
    short_name = str(row.get("SEC_NAME") or "").strip()
    volume_10k = normalize_decimal(row.get("TOT_VOL"))
    shares = int((Decimal(volume_10k) * Decimal("10000")).to_integral_value())

    return EtfShare(
        stat_date=str(row.get("STAT_DATE") or fallback_date),
        code=str(row.get("SEC_CODE") or "").strip(),
        name=short_name,
        short_name=short_name,
        etf_type=str(row.get("ETF_TYPE") or ""),
        total_volume_10k=volume_10k,
        total_volume_shares=shares,
    )
