<template>
  <section class="page" data-module="drain">
    <header class="page-head">
      <div>
        <h2>排水设施管理</h2>
        <p class="page-desc">维护排水设施，围绕设施编号、设施类型、所在道路、检查井数量做登记、筛选与状态流转。</p>
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

    <div class="tab-bar" role="tablist">
      <button
        class="tab"
        :class="{ active: activeTab === 'ledger' }"
        type="button"
        role="tab"
        @click="switchTab('ledger')"
      >
        清疏台账
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'plan' }"
        type="button"
        role="tab"
        @click="switchTab('plan')"
      >
        清疏计划（按下次清疏日）
      </button>
    </div>

    <!-- 清疏台账 -->
    <template v-if="activeTab === 'ledger'">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>设施编号</span>
          <input v-model="filters.keyword" placeholder="按设施编号检索" />
        </label>
        <label class="filter-item">
          <span>设施状态</span>
          <select v-model="filters.status">
            <option value="">全部状态</option>
            <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
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
            <th>明细</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <span v-if="column === '设施状态'" class="tag" :class="statusClass(String(row[column]))">{{ row[column] ?? '—' }}</span>
              <span v-else>{{ row[column] ?? '—' }}</span>
            </td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                :disabled="!canRunAction(action, row)"
                :title="actionBlockReason(action, row) ?? undefined"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
            <td>
              <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的排水设施记录</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条排水设施记录</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
        <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
      </footer>
    </template>

    <!-- 清疏计划：已停用、堵塞待修不进计划，按下次清疏日从早到晚 -->
    <template v-else>
      <p class="plan-tip">计划仅纳入「正常使用、待清疏」设施，已停用与堵塞待修设施不排入；到期后由责任班组跟进作业。</p>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in planColumns" :key="column">{{ column }}</th>
            <th>跟进安排</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in planRows" :key="String(row.id)">
            <td v-for="column in planColumns" :key="column">
              <span v-if="column === '设施状态'" class="tag" :class="statusClass(String(row[column]))">{{ row[column] ?? '—' }}</span>
              <span v-else>{{ row[column] ?? '—' }}</span>
            </td>
            <td class="row-actions">
              <template v-if="String(row['设施状态']) === '待清疏'">
                <span class="muted-text">已安排，等待{{ row['责任班组'] || '责任班组' }}作业，可在回执后确认正常</span>
              </template>
              <template v-else>
                <button
                  class="link"
                  :disabled="!canRunAction('安排清疏', row)"
                  :title="actionBlockReason('安排清疏', row) ?? undefined"
                  type="button"
                  @click="runAction('安排清疏', row)"
                >
                  安排清疏
                </button>
              </template>
            </td>
          </tr>
          <tr v-if="!planRows.length">
            <td :colspan="planColumns.length + 1" class="empty-state">当前没有需要排期的清疏任务</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ planRows.length }} 条待跟进清疏任务</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
        <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
      </footer>
    </template>

    <!-- 详情弹窗：明细字段与列表同口径 -->
    <div v-if="detail" class="modal-mask" role="dialog" aria-modal="true" @click.self="closeDetail">
      <div class="modal">
        <header class="modal-head">
          <h3>排水设施详情 · {{ detail['设施编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>
              <span v-if="column === '设施状态'" class="tag" :class="statusClass(String(detail[column]))">{{ detail[column] ?? '—' }}</span>
              <span v-else>{{ detail[column] ?? '—' }}</span>
            </dd>
          </template>
        </dl>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { ADMIN_ROLE, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type Tab = 'ledger' | 'plan'

const ENDPOINT = '/api/drain'
const columns = ['设施编号', '设施类型', '所在道路', '检查井数量', '上次清疏日', '下次清疏日', '责任班组', '设施状态']
const planColumns = ['设施编号', '设施类型', '所在道路', '检查井数量', '下次清疏日', '责任班组', '设施状态']
const actions = ['安排清疏', '确认正常', '停用设施']
const statuses = ['待清疏', '正常使用', '堵塞待修', '已停用']

const session = useSessionStore()

const stats = ref([
  { label: '在册排水设施', value: 0 },
  { label: '待清疏设施', value: 0 },
  { label: '堵塞待修', value: 0 },
])
const rows = ref<Row[]>([])
const planRows = ref<Row[]>([])
const total = ref(0)
const activeTab = ref<Tab>('ledger')
const errorMessage = ref('')
const successMessage = ref('')
const detail = ref<Row | null>(null)
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })

// 动作在各设施状态下是否适用（与后端 ACTION_RULES 口径一致）
const APPLICABLE: Record<string, string[]> = {
  安排清疏: ['正常使用'],
  确认正常: ['待清疏', '堵塞待修'],
  停用设施: ['正常使用', '待清疏'],
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function switchTab(tab: Tab) {
  activeTab.value = tab
  errorMessage.value = ''
  successMessage.value = ''
  void (tab === 'plan' ? loadPlan() : reload())
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '排水设施登记入口尚未接入审批流'
}

function statusClass(status: string): string {
  return {
    待清疏: 'tag-pending',
    正常使用: 'tag-normal',
    堵塞待修: 'tag-blocked',
    已停用: 'tag-disabled',
  }[status] ?? ''
}

// 越权与状态校验前置：返回不能执行的原因，null 表示可以提交
function actionBlockReason(action: string, row: Row): string | null {
  if (!session.canOperate) {
    return '未识别到值班身份，请先登录后再操作'
  }
  if (action === '停用设施' && !session.isAdmin) {
    return `动作「停用设施」仅限${ADMIN_ROLE}执行`
  }
  const ownerCrew = String(row['责任班组'] ?? '').trim()
  if (!session.isAdmin && ownerCrew && session.crew && session.crew !== ownerCrew) {
    return `该设施由「${ownerCrew}」负责，当前账号无权${action}`
  }
  const status = String(row['设施状态'] ?? '')
  if (!APPLICABLE[action].includes(status)) {
    return `设施当前为「${status}」，不能执行${action}`
  }
  return null
}

function canRunAction(action: string, row: Row): boolean {
  return actionBlockReason(action, row) === null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  const reason = actionBlockReason(action, row)
  if (reason) {
    errorMessage.value = reason
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      headers: identityHeaders(),
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    // HTTP 403 为越权拦截；ok=False 为状态口径等业务拦截，都要给操作者明确交代
    if (!response.ok) {
      throw new Error(payload?.message || '排水设施动作未生效，请稍后重试')
    }
    if (!payload?.ok) {
      throw new Error(payload?.message || '排水设施动作未生效')
    }
    successMessage.value = payload.message || '动作已生效'
    await Promise.all([reloadStats(), reload(), loadPlan()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施操作失败'
  }
}

function identityHeaders(): Record<string, string> {
  // HTTP 头只允许 latin-1，中文身份做百分号编码，由后端解码
  return {
    'X-Operator': encodeURIComponent(session.operator),
    'X-Operator-Role': encodeURIComponent(session.role),
    'X-Operator-Crew': encodeURIComponent(session.crew),
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('排水设施详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const data = (await response.json()) as Record<string, number>
    stats.value[0].value = data.total ?? 0
    stats.value[1].value = data.pending ?? 0
    stats.value[2].value = data.blocked ?? 0
  } catch {
    // 统计失败不阻塞台账使用，保持原值
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword.trim()) {
    query.set('keyword', filters.keyword.trim())
  }
  if (filters.status) {
    query.set('status', filters.status)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('排水设施列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '排水设施列表读取失败'
  }
}

async function loadPlan() {
  try {
    const response = await request(`${ENDPOINT}/plan`)
    if (!response.ok) {
      throw new Error('清疏计划读取失败')
    }
    const payload = (await response.json()) as { items?: Row[] }
    planRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '清疏计划读取失败'
  }
}

onMounted(() => {
  void reloadStats()
  void reload()
})
</script>

<style scoped>
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.tab {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px 6px 0 0;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
}
.tab.active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}
.plan-tip {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 8px;
}
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.tag-pending {
  background: #fef3c7;
  color: #92400e;
}
.tag-normal {
  background: #dcfce7;
  color: #166534;
}
.tag-blocked {
  background: #fee2e2;
  color: #991b1b;
}
.tag-disabled {
  background: #e5e7eb;
  color: #4b5563;
}
.success-text {
  color: #166534;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
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
.modal {
  background: #fff;
  border-radius: 8px;
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
  grid-template-columns: 110px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
</style>
