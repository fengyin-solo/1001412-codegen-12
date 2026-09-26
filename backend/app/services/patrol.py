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
SUBMITTED_STATUS = "已提交"
VOIDED_STATUS = "已作废"


def _parse_date(value: Any) -> date | None:
    """把「2026-09-26」这类字符串解析成日期，解析不了就返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _to_int(value: Any) -> int:
    """发现问题数可能是字符串或空值，统一折成非负整数。"""
    try:
        return max(int(float(str(value).strip())), 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float | None:
    """巡查里程只接受可解析的数字，其余按缺失处理、不进平均值。"""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _order_fact(order: dict[str, Any]) -> dict[str, Any]:
    """把一条巡查单折算成统计事实：作废单只记作废数，不进问题数与里程。"""
    voided = order.get("status") == VOIDED_STATUS
    problems = 0 if voided else _to_int(order.get("发现问题数"))
    mileage = None if voided else _to_float(order.get("巡查里程"))
    return {
        "problems": problems,
        "abnormal": not voided and problems > 0,
        "submitted": order.get("status") == SUBMITTED_STATUS,
        "voided": voided,
        "mileage": mileage,
    }


def _new_bucket() -> dict[str, Any]:
    return {
        "problem_count": 0,
        "abnormal_orders": 0,
        "submitted": 0,
        "voided": 0,
        "order_count": 0,
        "mileage_sum": 0.0,
        "mileage_count": 0,
    }


def _bucket_for(groups: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    return groups.setdefault(name, _new_bucket())


def _accumulate(bucket: dict[str, Any], fact: dict[str, Any]) -> None:
    bucket["order_count"] += 1
    bucket["problem_count"] += fact["problems"]
    bucket["abnormal_orders"] += 1 if fact["abnormal"] else 0
    bucket["submitted"] += 1 if fact["submitted"] else 0
    bucket["voided"] += 1 if fact["voided"] else 0
    if fact["mileage"] is not None:
        bucket["mileage_sum"] += fact["mileage"]
        bucket["mileage_count"] += 1


def _finalize(bucket: dict[str, Any]) -> dict[str, Any]:
    """输出分组结果：里程均值保留两位小数，没有里程数据时给空值而不是 0。"""
    mileage_count = bucket["mileage_count"]
    return {
        "problem_count": bucket["problem_count"],
        "abnormal_orders": bucket["abnormal_orders"],
        "submitted": bucket["submitted"],
        "voided": bucket["voided"],
        "order_count": bucket["order_count"],
        "avg_mileage": round(bucket["mileage_sum"] / mileage_count, 2) if mileage_count else None,
    }


def _finalize_groups(groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """分组按发现问题数降序排列，问题数相同再按名称排，方便先看问题多的。"""
    rows = [{"name": name, **_finalize(bucket)} for name, bucket in groups.items()]
    rows.sort(key=lambda row: (-int(row["problem_count"]), str(row["name"])))
    return rows


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

    def stats_overview(self, *, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """巡查问题分布统计：按路线与人员分组，同一巡查单只统计一次。

        口径约定：
        - 日期范围按「巡查日期」过滤，只给一端时按开区间处理，都不给则统计全部；
        - 同一「巡查单号」重复出现时只取第一次出现的记录，避免重复计数；
        - 作废巡查单不计入发现问题数、异常巡查单与平均里程，只在「作废巡查单」列单独体现；
        - 异常巡查单 = 未作废且发现问题数大于 0 的巡查单，问题数为零的单子不混入；
        - 平均巡查里程只取未作废且里程可解析为数字的巡查单。
        """
        start_date = _parse_date(start)
        end_date = _parse_date(end)
        orders = self._unique_orders(start_date, end_date)
        groups = {"by_route": {}, "by_person": {}}
        totals = _new_bucket()
        for order in orders:
            fact = _order_fact(order)
            _accumulate(totals, fact)
            _accumulate(_bucket_for(groups["by_route"], str(order.get("巡查路线") or "").strip() or "未填写"), fact)
            _accumulate(_bucket_for(groups["by_person"], str(order.get("巡查人员") or "").strip() or "未填写"), fact)
        return {
            "range": {"start": start, "end": end},
            "totals": _finalize(totals),
            "by_route": _finalize_groups(groups["by_route"]),
            "by_person": _finalize_groups(groups["by_person"]),
            "orders": orders,
        }

    def _unique_orders(self, start: date | None, end: date | None) -> list[dict[str, Any]]:
        """按日期范围过滤并按巡查单号去重，保证同一巡查单只统计一次。"""
        seen: set[str] = set()
        orders: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            key = str(row.get("巡查单号") or "").strip() or f"id:{row.get('id')}"
            if key in seen:
                continue
            if start is not None or end is not None:
                patrol_date = _parse_date(row.get("巡查日期"))
                if patrol_date is None:
                    continue
                if start is not None and patrol_date < start:
                    continue
                if end is not None and patrol_date > end:
                    continue
            seen.add(key)
            orders.append(row)
        return orders
