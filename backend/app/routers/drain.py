"""排水设施接口：维护排水设施，覆盖安排清疏、确认正常、停用设施等动作。"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.drain import (
    ADMIN_ROLE,
    ALL_STATUSES,
    PermissionError as DrainPermissionError,
    drain_service,
)

router = APIRouter(prefix="/api/drain", tags=["排水设施"])

LIST_FIELDS = ["设施编号", "设施类型", "所在道路", "检查井数量", "上次清疏日", "下次清疏日", "责任班组", "设施状态"]


def _operator_identity(
    x_operator: str | None,
    x_operator_role: str | None,
    x_operator_crew: str | None,
) -> tuple[str, str, str]:
    """从请求头解析操作人：姓名、角色、所属班组。

    HTTP 头只允许 latin-1，前端对中文身份做百分号编码，这里统一解码；
    身份缺失时按未登录处理，由动作入口拦截。
    """
    def decode(value: str | None) -> str:
        text = (value or "").strip()
        try:
            return unquote(text).strip()
        except (ValueError, TypeError):
            return text

    operator = decode(x_operator)
    # 角色不随缺省值放宽：身份头里没给角色就视为无角色，避免普通账号被当成管理员
    role = decode(x_operator_role)
    crew = decode(x_operator_crew)
    return operator, role, crew


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
    if status is not None and status not in ALL_STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(ALL_STATUSES)}")
    items, total = drain_service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """台账计数：在册、待清疏、正常使用、堵塞待修、已停用件数。"""
    return drain_service.stats()


@router.get("/plan")
def cleaning_plan() -> dict[str, Any]:
    """按下次清疏日排出的清疏计划；已停用与堵塞待修设施不在其中。"""
    return drain_service.cleaning_plan()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出排水设施清单：返回当前台账全量数据（含全部状态）。"""
    items, total = drain_service.list_entries(page=1, size=10000)
    return {"module": "drain", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条排水设施明细；不存在时给出可读的错误说明。"""
    entry = drain_service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"排水设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条排水设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = drain_service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="排水设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
    x_operator_crew: str | None = Header(default=None),
) -> ActionResult:
    """对单条排水设施执行安排清疏、确认正常、停用设施。

    越权（未登录、非管理员执行停用、跨责任班组下达动作）直接返回 403；
    状态不允许等业务拦截返回 ok=False 并说明原因，不再静默失败。
    """
    action = str(payload.values.get("action") or "").strip()
    operator, role, crew = _operator_identity(x_operator, x_operator_role, x_operator_crew)
    try:
        entry, message = drain_service.run_action(
            entry_id,
            action,
            operator=operator,
            role=role,
            crew=crew,
        )
    except DrainPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
