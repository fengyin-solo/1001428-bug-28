"""排水设施业务规则：状态流转、字段校验、清疏计划口径与越权校验都收在这里。

状态口径（设施状态字段与内部 status 保持一致）：
- 待清疏：已列入清疏计划，等待责任班组进场作业；
- 正常使用：通水正常，按下次清疏日排入计划即可；
- 堵塞待修：管道堵塞、须先维修，不允许直接安排清疏；
- 已停用：设施报废或长期停用，不再参与任何计划与动作。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "drain"
REQUIRED_FIELDS = ["设施编号", "设施类型", "所在道路"]
STATUS_PENDING = "待清疏"
STATUS_NORMAL = "正常使用"
STATUS_BLOCKED = "堵塞待修"
STATUS_DISABLED = "已停用"
# 不再当作有先后顺序的序列：堵塞待修是异常态，已停用是终态，不参与状态推进
ALL_STATUSES = [STATUS_PENDING, STATUS_NORMAL, STATUS_BLOCKED, STATUS_DISABLED]
# 已停用与堵塞待修的设施不进清疏计划
PLAN_EXCLUDED_STATUSES = [STATUS_DISABLED, STATUS_BLOCKED]
ABNORMAL_STATUSES = [STATUS_BLOCKED]
ACTIVE_STATUSES = [STATUS_PENDING, STATUS_NORMAL]

# 各动作允许的前置状态与目标状态：
# 安排清疏只推进到「待清疏」，后续由责任班组按计划跟进；
# 确认正常表示清疏/维修回执确认通水正常，落回「正常使用」；
# 停用设施只在正常使用、待清疏时可执行，堵塞待修须先走维修闭环。
ACTION_RULES: dict[str, dict[str, Any]] = {
    "安排清疏": {
        "target": STATUS_PENDING,
        "allowed_from": [STATUS_NORMAL],
        "reject": {
            STATUS_PENDING: "设施已在清疏计划内（待清疏），请勿重复安排，后续由责任班组跟进作业",
            STATUS_BLOCKED: "设施处于堵塞待修，须先完成维修并确认正常，不能直接安排清疏",
            STATUS_DISABLED: "设施已停用，不再安排清疏",
        },
        "success": "已排入清疏计划（待清疏），由责任班组按下次清疏日跟进作业",
    },
    "确认正常": {
        "target": STATUS_NORMAL,
        "allowed_from": [STATUS_PENDING, STATUS_BLOCKED],
        "reject": {
            STATUS_NORMAL: "设施已确认为正常使用，无需重复确认",
            STATUS_DISABLED: "设施已停用，不能确认正常；如需复用请先重新登记启用",
        },
        "success": "回执已确认：设施状态落回正常使用",
    },
    "停用设施": {
        "target": STATUS_DISABLED,
        "allowed_from": [STATUS_NORMAL, STATUS_PENDING],
        "reject": {
            STATUS_BLOCKED: "设施处于堵塞待修，须先完成维修闭环后再停用",
            STATUS_DISABLED: "设施已停用，无需重复操作",
        },
        "success": "设施已停用，将不再排入清疏计划",
    },
}
# 停用设施属于管理动作，仅值班管理员可执行
ADMIN_ONLY_ACTIONS = ["停用设施"]
ADMIN_ROLE = "值班管理员"


class PermissionError(Exception):
    """越权或身份缺失：由路由层翻译成 403。"""


class DrainService:
    # ---------- 查询 ----------
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
            rows = [row for row in rows if keyword in str(row.get("设施编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, Any]:
        """台账计数：件数与列表、详情共用同一状态口径。"""
        rows = store.rows(MODULE)
        return {
            "total": len(rows),
            "pending": sum(1 for row in rows if row.get("status") == STATUS_PENDING),
            "normal": sum(1 for row in rows if row.get("status") == STATUS_NORMAL),
            "blocked": sum(1 for row in rows if row.get("status") == STATUS_BLOCKED),
            "disabled": sum(1 for row in rows if row.get("status") == STATUS_DISABLED),
        }

    def cleaning_plan(self) -> dict[str, Any]:
        """按下次清疏日排出的清疏计划。

        只纳入正常使用与待清疏设施；已停用、堵塞待修一律不进计划。
        排序按下次清疏日从早到晚，日期缺失或无法识别的排到最后。
        """
        rows = [row for row in store.rows(MODULE) if row.get("status") not in PLAN_EXCLUDED_STATUSES]
        rows.sort(key=lambda row: (self._date_key(row.get("下次清疏日")) is None, self._date_key(row.get("下次清疏日")) or date.max))
        return {"total": len(rows), "items": rows}

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 原排水设施字段照旧：只落必填字段，其余字段留待台账补录
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_NORMAL
        entry["设施状态"] = STATUS_NORMAL
        entry["pending"] = False
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    # ---------- 动作 ----------
    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str,
        role: str,
        crew: str,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"排水设施 {entry_id} 不存在或已归档"
        if not operator:
            raise PermissionError("未识别到操作人身份，请先登录值班账号后再提交")
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于排水设施可执行范围"

        is_admin = role == ADMIN_ROLE
        if action in ADMIN_ONLY_ACTIONS and not is_admin:
            raise PermissionError(f"动作「{action}」仅限值班管理员执行，当前身份为「{role or '未知'}」")

        current = str(entry.get("status") or "")
        rule = ACTION_RULES[action]
        if current not in rule["allowed_from"]:
            return None, rule["reject"].get(current, f"设施当前为「{current}」，不能执行{action}")

        # 非管理员只能对本责任班组的设施下达动作；管理员可跨班组调度
        owner_crew = str(entry.get("责任班组") or "").strip()
        if not is_admin and owner_crew and crew and crew != owner_crew:
            raise PermissionError(f"该设施由「{owner_crew}」负责，当前账号属于「{crew}」，无权{action}")

        target = rule["target"]
        entry["status"] = target
        entry["设施状态"] = target
        entry["pending"] = target == STATUS_PENDING
        entry["abnormal"] = target in ABNORMAL_STATUSES
        return entry, str(rule["success"])

    # ---------- 内部工具 ----------
    @staticmethod
    def _date_key(value: Any) -> date | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


drain_service = DrainService()
