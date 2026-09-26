<template>
  <section class="page" data-module="drain">
    <header class="page-head">
      <div>
        <h2>排水设施管理</h2>
        <p class="page-desc">
          维护排水设施，围绕设施编号、设施类型、所在道路、检查井数量做登记、筛选与状态流转；
          当前操作角色：{{ session.role }}。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记排水设施</button>
        <button class="btn" type="button" @click="exportRows">导出排水设施清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="plan-panel">
      <header class="plan-head">
        <h3>清疏计划（按下次清疏日升序）</h3>
        <span class="plan-note">仅排入「待清疏」与到期的「正常使用」设施；堵塞待修、已停用不参与排班。共 {{ planTotal }} 件。</span>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>设施编号</th><th>设施类型</th><th>所在道路</th><th>下次清疏日</th><th>责任班组</th><th>设施状态</th><th>计划口径</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in planRows" :key="`plan-${String(row.id)}`">
            <td><button class="link" type="button" @click="openDetail(row.id)">{{ row['设施编号'] }}</button></td>
            <td>{{ row['设施类型'] }}</td>
            <td>{{ row['所在道路'] }}</td>
            <td>{{ row['下次清疏日'] }}</td>
            <td>{{ row['责任班组'] }}</td>
            <td>{{ row['设施状态'] }}</td>
            <td>{{ row['计划口径'] }}</td>
          </tr>
          <tr v-if="!planRows.length">
            <td colspan="7" class="empty-state">当前没有待清疏或到期待安排的设施</td>
          </tr>
        </tbody>
      </table>
    </section>

    <form class="filter-bar" @submit.prevent="() => reload()">
      <label class="filter-item">
        <span>设施编号</span>
        <input v-model="keyword" placeholder="按设施编号检索" />
      </label>
      <label class="filter-item">
        <span>设施状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '设施编号'" class="link" type="button" @click="openDetail(row.id)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!actionEnabled(action, row)"
              :title="actionHint(action, row)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无排水设施数据，可先登记排水设施</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条排水设施记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="infoMessage" class="info-text">{{ infoMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card" role="dialog" aria-modal="true" aria-label="排水设施详情">
        <header class="modal-head">
          <h3>排水设施详情 · {{ detail['设施编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-item">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </div>
          <div class="detail-item detail-wide">
            <dt>跟进说明</dt>
            <dd>{{ detail['跟进说明'] ?? '暂无跟进说明' }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request, resolveErrorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

interface Summary {
  total: number
  待清疏: number
  正常使用: number
  堵塞待修: number
  已停用: number
}

interface PlanItem extends Row {
  计划口径: string
}

const ENDPOINT = '/api/drain'
const columns = ["设施编号", "设施类型", "所在道路", "检查井数量", "上次清疏日", "下次清疏日", "责任班组", "设施状态"]
const detailFields = columns
const actions = ["安排清疏", "确认正常", "停用设施"] as const
const statuses = ["待清疏", "正常使用", "堵塞待修", "已停用"]

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const planRows = ref<PlanItem[]>([])
const planTotal = ref(0)
const summary = ref<Summary>({ total: 0, 待清疏: 0, 正常使用: 0, 堵塞待修: 0, 已停用: 0 })
const stats = ref([
  { label: '在册排水设施', value: 0 },
  { label: '待清疏设施', value: 0 },
  { label: '堵塞待修', value: 0 },
  { label: '已停用', value: 0 },
])

const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const infoMessage = ref('')
const detail = ref<Row | null>(null)

/** 动作与当前状态是否匹配；与后端状态机保持一致，仅用于提前置灰。 */
function actionEnabled(action: string, row: Row): boolean {
  if (!session.canRunAction(action)) {
    return false
  }
  const status = String(row['设施状态'] ?? '')
  if (action === '安排清疏') {
    return status === '正常使用'
  }
  if (action === '确认正常') {
    return status === '待清疏' || status === '堵塞待修'
  }
  if (action === '停用设施') {
    return status !== '已停用'
  }
  return false
}

function actionHint(action: string, row: Row): string {
  if (!session.canRunAction(action)) {
    return `当前角色「${session.role}」无权执行「${action}」，需${session.requiredRole(action)}处理`
  }
  const status = String(row['设施状态'] ?? '')
  if (action === '安排清疏') {
    if (status === '待清疏') {
      return '已在待清疏队列，等待清疏回执'
    }
    if (status === '堵塞待修') {
      return '堵塞待修设施需先维修并确认正常，不能安排清疏'
    }
    if (status === '已停用') {
      return '已停用设施不能排进清疏计划'
    }
  }
  if (action === '确认正常' && status === '正常使用') {
    return '设施当前已是正常使用'
  }
  if (action === '确认正常' && status === '已停用') {
    return '已停用设施不能确认正常'
  }
  if (action === '停用设施' && status === '已停用') {
    return '设施已处于停用状态'
  }
  return action
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '排水设施登记入口尚未接入审批流'
  infoMessage.value = ''
}

async function openDetail(id: number | string | null) {
  if (id == null) {
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      throw new Error(await resolveErrorMessage(response, '排水设施详情读取失败'))
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
      role: session.roleCode(),
    })
    const payload = (await response.json()) as { ok?: boolean; message?: string; detail?: string }
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.detail || payload.message || '排水设施动作未生效，请稍后重试')
    }
    infoMessage.value = payload.message || '动作已执行'
    await Promise.all([reload(false), loadSummary(), loadPlan()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施操作失败'
  }
}

async function reload(announce = true) {
  if (announce) {
    errorMessage.value = ''
    infoMessage.value = ''
  }
  const params = new URLSearchParams()
  if (keyword.value) {
    params.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error(await resolveErrorMessage(response, '排水设施列表读取失败'))
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施列表读取失败'
  }
}

async function loadSummary() {
  const response = await request(`${ENDPOINT}/summary`)
  if (!response.ok) {
    return
  }
  summary.value = await response.json()
  stats.value = [
    { label: '在册排水设施', value: summary.value.total },
    { label: '待清疏设施', value: summary.value.待清疏 },
    { label: '堵塞待修', value: summary.value.堵塞待修 },
    { label: '已停用', value: summary.value.已停用 },
  ]
}

async function loadPlan() {
  try {
    const response = await request(`${ENDPOINT}/cleaning-plan`)
    if (!response.ok) {
      throw new Error(await resolveErrorMessage(response, '清疏计划读取失败'))
    }
    const payload = (await response.json()) as { items?: PlanItem[]; total?: number }
    planRows.value = payload.items ?? []
    planTotal.value = payload.total ?? planRows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '清疏计划读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
  void loadPlan()
})
</script>

<style scoped>
.plan-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.plan-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}
.plan-head h3 {
  font-size: 14px;
  margin: 0;
}
.plan-note {
  color: var(--muted);
  font-size: 12px;
}
.info-text {
  color: #176b3a;
}
.link:disabled {
  color: #9aa4b2;
  cursor: not-allowed;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 10px;
  width: 560px;
  max-width: calc(100vw - 32px);
  padding: 16px 20px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  margin: 0;
}
.detail-item dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-item dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.detail-wide {
  grid-column: 1 / -1;
}
</style>
