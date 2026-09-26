import { defineStore } from 'pinia'

/** 排水设施动作的可执行角色；越权提交会被后端以 403 拦下，前端同时置灰提示。 */
const ACTION_ROLE_LABEL: Record<string, string> = {
  安排清疏: '班组长',
  确认正常: '班组长',
  停用设施: '管理员',
}

/** 角色中文口径 -> 请求头 X-Operator-Role 使用的 ASCII 代码。 */
const ROLE_CODES = {
  值班员: 'clerk',
  班组长: 'leader',
  管理员: 'admin',
} as const

export const ROLES = ['值班员', '班组长', '管理员'] as const
export type OperatorRole = (typeof ROLES)[number]

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '值班员' as OperatorRole,
    shiftLabel: '白班 08:00-20:00',
    scope: '市政道路桥梁养护平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: OperatorRole) {
      this.role = role
    },
    roleCode(): string {
      return ROLE_CODES[this.role]
    },
    canRunAction(action: string): boolean {
      const required = ACTION_ROLE_LABEL[action]
      if (!required) {
        return false
      }
      return this.role === '管理员' || this.role === required
    },
    requiredRole(action: string): string {
      return ACTION_ROLE_LABEL[action] ?? ''
    },
  },
})
