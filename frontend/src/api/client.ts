/** 统一请求封装：拼后端地址、带上当前值班角色、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export interface RequestOptions extends RequestInit {
  /** 当前操作角色，写入 X-Operator-Role 供后端做越权校验。 */
  role?: string
}

export function request(path: string, init?: RequestOptions): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const { role, headers, ...rest } = init ?? {}
  const finalHeaders = new Headers(headers)
  finalHeaders.set('Content-Type', 'application/json')
  if (role) {
    finalHeaders.set('X-Operator-Role', role)
  }
  return fetch(url, { headers: finalHeaders, ...rest }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** 取出后端业务/越权拦截里的可读说明；没有时退回调用方给的兜底文案。 */
export async function resolveErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string }
    return payload.detail || payload.message || fallback
  } catch {
    return fallback
  }
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
