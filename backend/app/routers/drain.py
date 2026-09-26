"""排水设施接口：维护排水设施，覆盖清疏计划、安排清疏、确认正常、停用设施等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.drain import DrainService, normalize_role

router = APIRouter(prefix="/api/drain", tags=["排水设施"])

service = DrainService()

LIST_FIELDS = ["设施编号", "设施类型", "所在道路", "检查井数量", "上次清疏日", "下次清疏日", "责任班组", "设施状态"]
STATUSES = ["待清疏", "正常使用", "堵塞待修", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设施编号检索"),
    status: str | None = Query(default=None, description="待清疏、正常使用、堵塞待修、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设施编号与状态过滤排水设施列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(STATUSES)}")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def drain_summary() -> dict[str, int]:
    """排水台账状态件数：与列表、详情共用同一份台账数据。"""
    return service.summary()


@router.get("/cleaning-plan")
def cleaning_plan() -> dict[str, Any]:
    """清疏计划：只含待清疏与到期正常使用设施，按下次清疏日升序。"""
    items, total = service.cleaning_plan()
    return {"items": items, "total": total}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出排水设施清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "drain", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条排水设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"排水设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条排水设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="排水设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str = Header(default="", alias="X-Operator-Role"),
) -> ActionResult:
    """对单条排水设施执行安排清疏、确认正常、停用设施。

    越权提交先于状态变更校验，直接返回 403 并说明所需角色；其余业务拦截返回 ok=False。
    请求头 X-Operator-Role 携带角色代码：clerk 值班员 / leader 班组长 / admin 管理员。
    """
    action = str(payload.values.get("action") or "").strip()
    role = normalize_role(x_operator_role)
    entry, message, forbidden = service.run_action(entry_id, action, role)
    if forbidden:
        raise HTTPException(status_code=403, detail=message)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
