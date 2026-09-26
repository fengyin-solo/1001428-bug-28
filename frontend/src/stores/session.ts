import { defineStore } from 'pinia'

export const ADMIN_ROLE = '值班管理员'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: ADMIN_ROLE,
    // 默认管理员班组留空，表示可跨班组调度；普通作业账号应填上所属责任班组
    crew: '',
    shiftLabel: '白班 08:00-20:00',
    scope: '市政道路桥梁养护平台',
  }),
  getters: {
    canOperate: (state) => state.operator.trim().length > 0,
    isAdmin: (state) => state.role === ADMIN_ROLE,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
  },
})
