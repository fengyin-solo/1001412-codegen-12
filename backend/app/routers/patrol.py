"""巡查任务接口：维护巡查单，覆盖派发巡查、提交结果、作废巡查等动作。"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.patrol import PatrolService

router = APIRouter(prefix="/api/patrol", tags=["巡查任务"])

service = PatrolService()

LIST_FIELDS = ["巡查单号", "巡查路线", "巡查人员", "巡查日期", "巡查里程", "发现问题数", "巡查时长", "巡查状态"]
STATUSES = ["待派发", "巡查中", "已提交", "已作废"]


def _parse_range(value: str | None, label: str) -> date | None:
    """日期范围只接受 YYYY-MM-DD；格式不对时给出可读提示，不静默忽略。"""
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}格式应为 YYYY-MM-DD，收到的是「{value}」")


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按巡查单号检索"),
    status: str | None = Query(default=None, description="待派发、巡查中、已提交、已作废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按巡查单号与状态过滤巡查任务列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/distribution")
def distribution_overview(
    start: str | None = Query(default=None, description="起始日期 YYYY-MM-DD，含当天"),
    end: str | None = Query(default=None, description="截止日期 YYYY-MM-DD，含当天"),
) -> dict[str, Any]:
    """巡查问题分布概览：按路线与人员汇总问题数、已提交、作废单与平均里程。

    注意要注册在 /{entry_id} 之前，否则 "distribution" 会被当成巡查单 id 匹配走。
    """
    start_day = _parse_range(start, "起始日期")
    end_day = _parse_range(end, "截止日期")
    if start_day and end_day and start_day > end_day:
        raise HTTPException(status_code=400, detail="起始日期不能晚于截止日期，请调整日期范围")
    return service.distribution(start=start_day, end=end_day)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出巡查任务清单：返回当前过滤条件下的全量数据。需注册在 /{entry_id} 之前，否则会被当成单号 id。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "patrol", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条巡查单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"巡查单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条巡查单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="巡查单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条巡查单执行派发巡查、提交结果、作废巡查；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
