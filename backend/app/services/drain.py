"""排水设施业务规则：状态口径、清疏流转、清疏计划与越权校验都收在这里。

状态口径（唯一事实来源是内部 status，原“设施状态”字段在出参时与其对齐）：
- 待清疏：已安排清疏、等待清疏回执，属于待跟进；
- 正常使用：通水正常，无需作业；
- 堵塞待修：已堵塞，属于异常，需维修后由班组长确认正常，期间不得安排清疏；
- 已停用：设施报废停用，不再进入任何清疏计划。

动作流转：
- 安排清疏：正常使用 -> 待清疏，并交代由责任班组按下次清疏日跟进；
- 确认正常：待清疏（清疏回执）/ 堵塞待修（维修复核） -> 正常使用；
- 停用设施：非停用状态 -> 已停用。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "drain"
REQUIRED_FIELDS = ["设施编号", "设施类型", "所在道路"]
DISPLAY_STATUS_FIELD = "设施状态"
FOLLOW_UP_FIELD = "跟进说明"

PENDING_CLEAN = "待清疏"
NORMAL = "正常使用"
BLOCKED = "堵塞待修"
STOPPED = "已停用"
STATUS_ORDER = [PENDING_CLEAN, NORMAL, BLOCKED, STOPPED]

# 可进入清疏计划的状态：堵塞待修与已停用一律不得排入。
PLANABLE_STATUSES = {PENDING_CLEAN, NORMAL}

# 动作 -> 允许执行的角色；越权提交在状态变更前先行拦下。
# 角色经 X-Operator-Role 请求头传入（只能是 ASCII 代码），ROLE_LABELS 负责翻译成中文口径。
ROLE_LABELS = {"clerk": "值班员", "leader": "班组长", "admin": "管理员"}
ACTION_ROLES: dict[str, tuple[str, ...]] = {
    "安排清疏": ("leader", "admin"),
    "确认正常": ("leader", "admin"),
    "停用设施": ("admin",),
}


def normalize_role(role: str) -> str:
    """把请求头里的角色代码归一化；未知代码按值班员处理。"""
    code = (role or "clerk").strip().lower()
    return code if code in ROLE_LABELS else "clerk"


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class DrainService:
    # ---------- 读取 ----------
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
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._present(row) if row is not None else None

    def summary(self) -> dict[str, int]:
        """各状态件数，全部由同一份台账数据现算，保证与列表、详情口径一致。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        return {
            "total": len(store.rows(MODULE)),
            PENDING_CLEAN: counts[PENDING_CLEAN],
            NORMAL: counts[NORMAL],
            BLOCKED: counts[BLOCKED],
            STOPPED: counts[STOPPED],
        }

    def cleaning_plan(self, *, today: date | None = None) -> tuple[list[dict[str, Any]], int]:
        """清疏计划：待清疏件 + 已到期（下次清疏日 <= 今天）的正常使用件。

        已停用、堵塞待修不进计划；按下次清疏日从早到晚排，日期无法识别的沉底。
        """
        today = today or date.today()
        plan_rows: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            status = str(row.get("status") or "")
            next_day = _parse_day(row.get("下次清疏日"))
            if status == PENDING_CLEAN:
                scope = "已安排待清疏"
            elif status == NORMAL and next_day is not None and next_day <= today:
                scope = "到期待安排"
            else:
                continue
            item = self._present(row)
            item["计划口径"] = scope
            plan_rows.append(item)
        plan_rows.sort(key=lambda item: (
            0 if _parse_day(item.get("下次清疏日")) is not None else 1,
            _parse_day(item.get("下次清疏日")) or date.max,
        ))
        return plan_rows, len(plan_rows)

    # ---------- 写入 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        self._apply_status(entry, PENDING_CLEAN)
        rows.append(entry)
        return self._present(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        role: str,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行动作，返回 (明细, 说明, 是否越权)。越权时第三条为 True。"""
        if action not in ACTION_ROLES:
            return None, f"动作「{action}」不属于排水设施可执行范围", False
        # 越权先校验：在任何状态变更之前拦下。
        if role not in ACTION_ROLES[action]:
            allowed = "、".join(ROLE_LABELS[code] for code in ACTION_ROLES[action])
            return None, f"当前角色「{ROLE_LABELS.get(role, role)}」无权执行「{action}」，需{allowed}处理", True

        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"排水设施 {entry_id} 不存在或已归档", False

        status = str(entry.get("status") or "")
        crew = str(entry.get("责任班组") or "责任班组未指派")
        next_day = str(entry.get("下次清疏日") or "下次清疏日待定")

        if action == "安排清疏":
            if status == PENDING_CLEAN:
                return None, f"设施已在「待清疏」队列，由{crew}跟进，无需重复安排", False
            if status == BLOCKED:
                return None, "设施处于「堵塞待修」，需先维修并确认正常后才能安排清疏", False
            if status == STOPPED:
                return None, "设施已停用，不能再排进清疏计划", False
            self._apply_status(
                entry,
                PENDING_CLEAN,
                follow_up=f"已安排清疏，由{crew}按下次清疏日{next_day}跟进回执",
            )
            return (
                self._present(entry),
                f"已安排清疏，设施进入「待清疏」，由{crew}按下次清疏日{next_day}跟进",
                False,
            )

        if action == "确认正常":
            if status == NORMAL:
                return None, "设施当前已是「正常使用」，无需重复确认", False
            if status == STOPPED:
                return None, "设施已停用，不能确认正常；如需复用请先重新登记", False
            if status == PENDING_CLEAN:
                note = f"清疏回执已确认，{crew}办结"
                message = "清疏回执已确认，设施恢复「正常使用」"
            else:  # 堵塞待修
                note = f"维修复核通过，{crew}确认恢复通水"
                message = "维修复核通过，设施恢复「正常使用」"
            self._apply_status(entry, NORMAL, follow_up=note)
            return self._present(entry), message, False

        if action == "停用设施":
            if status == STOPPED:
                return None, "设施已处于「已停用」状态", False
            self._apply_status(entry, STOPPED, follow_up="设施已停用，不再进入清疏计划")
            return self._present(entry), "设施已停用，不再进入清疏计划", False

        return None, f"动作「{action}」不属于排水设施可执行范围", False

    # ---------- 内部工具 ----------
    def _apply_status(self, entry: dict[str, Any], status: str, *, follow_up: str | None = None) -> None:
        """统一写状态口径：status、pending、abnormal 与原“设施状态”字段保持一致。"""
        entry["status"] = status
        entry["pending"] = status == PENDING_CLEAN
        entry["abnormal"] = status == BLOCKED
        entry[DISPLAY_STATUS_FIELD] = status
        if follow_up is not None:
            entry[FOLLOW_UP_FIELD] = follow_up

    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """出参投影：原字段照旧，只把“设施状态”对齐到内部状态，保证列表与详情一致。"""
        item = dict(row)
        item[DISPLAY_STATUS_FIELD] = str(row.get("status") or "")
        return item
