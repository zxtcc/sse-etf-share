"""ETF 份额查询 Web 程序入口。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List

from flask import Flask, jsonify, render_template, request

import storage
from sse_client import EtfShare, SseClientError, SseEtfClient, validate_date


app = Flask(__name__)
client = SseEtfClient()
DEFAULT_START_DATE = "2023-01-01"
REQUEST_PAUSE_RANGE = (0.15, 0.45)


@app.get("/")
def index():
    return render_template(
        "index.html",
        default_start_date=DEFAULT_START_DATE,
        default_end_date=latest_non_weekend_date().isoformat(),
    )


@app.post("/api/query")
def query_etf_share():
    payload = request.get_json(silent=True) or request.form
    code = payload.get("code", "")
    stat_date = payload.get("date", "")

    try:
        normalized_date = validate_date(stat_date)
        cached = storage.load_share(code, normalized_date)
        if cached:
            return jsonify({"success": True, "source": "local", "data": cached.to_dict()})

        if storage.is_date_fully_updated(normalized_date):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "本地全量数据中未找到该 ETF 在指定日期的份额数据，请确认代码。",
                    }
                ),
                404,
            )

        data = client.fetch_share(code, normalized_date)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except SseClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    if data is None:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "未查询到该 ETF 在指定日期的份额数据，请确认代码或选择交易日。",
                }
            ),
            404,
        )

    storage.save_shares([data])
    return jsonify({"success": True, "source": "sse", "data": data.to_dict()})


@app.post("/api/update")
def update_etf_data():
    payload = request.get_json(silent=True) or request.form
    start = payload.get("start", DEFAULT_START_DATE)
    end = payload.get("end", latest_non_weekend_date().isoformat())

    try:
        start_date = parse_date(start)
        end_date = parse_date(end)
        if start_date > end_date:
            return jsonify({"success": False, "message": "起始日期不能晚于终止日期"}), 400
        latest_allowed = latest_non_weekend_date()
        if end_date > latest_allowed:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"终止日期不能晚于最近一个非周末日期 {latest_allowed.isoformat()}",
                    }
                ),
                400,
            )

        summary = run_data_update(start_date, end_date)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except SseClientError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    return jsonify({"success": True, "summary": summary})


def run_data_update(start_date: date, end_date: date):
    fetched_dates: List[str] = []
    skipped_full_dates: List[str] = []
    skipped_weekends: List[str] = []
    empty_dates: List[str] = []
    all_shares: List[EtfShare] = []
    full_date_counts = {}

    for current in iter_dates(start_date, end_date):
        stat_date = current.isoformat()
        if current.weekday() >= 5:
            skipped_weekends.append(stat_date)
            continue
        if storage.is_date_fully_updated(stat_date):
            skipped_full_dates.append(stat_date)
            continue

        shares = client.fetch_all_shares_for_date(
            stat_date,
            page_size=1000,
            pause_range=REQUEST_PAUSE_RANGE,
        )
        if shares:
            fetched_dates.append(stat_date)
            all_shares.extend(shares)
        else:
            empty_dates.append(stat_date)
        full_date_counts[stat_date] = len(shares)

    saved_records = storage.save_shares(all_shares)
    for stat_date, record_count in full_date_counts.items():
        storage.mark_date_fully_updated(stat_date, record_count)

    return {
        "date_count": len(list(iter_dates(start_date, end_date))),
        "fetched_date_count": len(fetched_dates),
        "skipped_full_date_count": len(skipped_full_dates),
        "skipped_weekend_count": len(skipped_weekends),
        "empty_date_count": len(empty_dates),
        "saved_record_count": saved_records,
        "fetched_dates": fetched_dates,
        "skipped_full_dates": skipped_full_dates,
        "empty_dates": empty_dates,
    }


def iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def parse_date(value: str) -> date:
    return datetime.strptime(validate_date(value), "%Y-%m-%d").date()


def latest_non_weekend_date() -> date:
    current = date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
