"""巡查任务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "patrol"
REQUIRED_FIELDS = ["巡查单号", "巡查路线", "巡查人员"]
STATUS_ORDER = ["待派发", "巡查中", "已提交", "已作废"]
ACTION_RULES = {"派发巡查": "巡查中", "提交结果": "已提交", "作废巡查": "已作废"}
NEGATIVE_ACTIONS = ["作废巡查"]
VOIDED_STATUS = "已作废"
SUBMITTED_STATUS = "已提交"


def _parse_number(value: Any) -> float | None:
    """把里程、问题数这类字段解析成数字；占位文本或空值返回 None，由调用方决定口径。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_day(value: Any) -> date | None:
    """巡查日期只认 YYYY-MM-DD；解析不了的记录不参与日期范围判断。"""
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


class PatrolService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("巡查单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡查单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于巡查任务可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"巡查单已{action}"

    def distribution(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """巡查问题分布概览：按巡查路线 × 巡查人员汇总。

        统计口径（与巡查单列表同源，保证两边数字对得上）：
        - 同一巡查单号只统计一次，重复登记的取先出现的一条；
        - 作废巡查单不计入发现问题数、不参与平均里程，单独列出作废单数；
        - 发现问题数为零的巡查单不算异常，异常单只统计问题数大于零的；
        - 指定日期范围时，巡查日期缺失或无法解析的巡查单不纳入。
        """
        orders = self._dedupe_orders(start=start, end=end)

        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for order in orders:
            key = (str(order.get("巡查路线") or "未填路线"), str(order.get("巡查人员") or "未填人员"))
            bucket = groups.setdefault(key, {
                "巡查路线": key[0],
                "巡查人员": key[1],
                "发现问题数": 0,
                "异常巡查单": 0,
                "已提交巡查单": 0,
                "作废巡查单": 0,
                "_里程合计": 0.0,
                "_里程单数": 0,
            })
            if order.get("status") == VOIDED_STATUS:
                bucket["作废巡查单"] += 1
                continue
            problems = _parse_number(order.get("发现问题数")) or 0.0
            bucket["发现问题数"] += int(problems)
            if problems > 0:
                bucket["异常巡查单"] += 1
            if order.get("status") == SUBMITTED_STATUS:
                bucket["已提交巡查单"] += 1
            mileage = _parse_number(order.get("巡查里程"))
            if mileage is not None:
                bucket["_里程合计"] += mileage
                bucket["_里程单数"] += 1

        rows = []
        for bucket in groups.values():
            mileage_count = bucket.pop("_里程单数")
            mileage_total = bucket.pop("_里程合计")
            bucket["平均巡查里程"] = round(mileage_total / mileage_count, 1) if mileage_count else 0.0
            rows.append(bucket)
        rows.sort(key=lambda row: (-int(row["发现问题数"]), -int(row["异常巡查单"]), row["巡查路线"], row["巡查人员"]))

        cards = [
            {"label": "发现问题总数", "value": sum(int(row["发现问题数"]) for row in rows)},
            {"label": "异常巡查单", "value": sum(int(row["异常巡查单"]) for row in rows)},
            {"label": "已提交巡查单", "value": sum(int(row["已提交巡查单"]) for row in rows)},
            {"label": "作废巡查单", "value": sum(int(row["作废巡查单"]) for row in rows)},
            {"label": "覆盖巡查路线", "value": len({row["巡查路线"] for row in rows})},
            {"label": "参与巡查人员", "value": len({row["巡查人员"] for row in rows})},
        ]
        return {"cards": cards, "groups": rows, "orders": orders}

    def _dedupe_orders(self, *, start: date | None, end: date | None) -> list[dict[str, Any]]:
        """按日期范围过滤并按巡查单号去重，结果按巡查日期从新到旧排列。"""
        seen: set[str] = set()
        orders: list[dict[str, Any]] = []
        rows = sorted(store.rows(MODULE), key=lambda row: int(row.get("id", 0)))
        for row in rows:
            day = _parse_day(row.get("巡查日期"))
            if (start or end) and day is None:
                continue
            if start and day and day < start:
                continue
            if end and day and day > end:
                continue
            number = str(row.get("巡查单号") or "").strip()
            key = f"no:{number}" if number else f"id:{row.get('id', 0)}"
            if key in seen:
                continue
            seen.add(key)
            orders.append(row)
        orders.sort(key=lambda row: (str(row.get("巡查日期") or ""), -int(row.get("id", 0))), reverse=True)
        return orders
