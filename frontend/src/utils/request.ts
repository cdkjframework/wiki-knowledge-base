/**
 * 通用 HTTP 方法扩展（含 DELETE、FormData 上传）。
 */
import axios, { type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

const UNKNOWN_ERROR = '未知错误，请重试'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 120000,
})

service.interceptors.request.use(
  (config) => {
    if (config.headers) {
      config.headers['X-Requested-With'] = 'XMLHttpRequest'
      // FormData 交由浏览器设置 multipart boundary
      if (config.data instanceof FormData) {
        delete config.headers['Content-Type']
      } else if (!config.headers['Content-Type']) {
        config.headers['Content-Type'] = 'application/json'
      }
    }
    return config
  },
  (error: Error) => Promise.reject(error),
)

service.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data
    if (response.status !== 200) {
      ElMessage.error((res && res.message) || UNKNOWN_ERROR)
      return Promise.reject(res)
    }
    if (res && typeof res === 'object' && 'code' in res) {
      const code = Number(res.code)
      if (code !== 0 && code !== 200) {
        ElMessage.error(res.message || res.error || UNKNOWN_ERROR)
        return Promise.reject(res)
      }
    }
    return response
  },
  (error) => {
    if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请稍后重试')
      return Promise.reject(error)
    }
    const errMsg = error?.response?.data?.message || error?.response?.data?.error || error.message || UNKNOWN_ERROR
    ElMessage.error(String(errMsg))
    return Promise.reject(error)
  },
)

export async function request<T = unknown>(config: AxiosRequestConfig): Promise<T> {
  const response = await service.request(config)
  const body = response.data as T & { data?: T; code?: number; error?: string }
  if (body && typeof body === 'object' && 'data' in body && 'code' in body) {
    return (body as { data: T }).data
  }
  return body as T
}

export function get<T = unknown>(url: string, params?: object, config?: AxiosRequestConfig) {
  return request<T>({ ...config, url, method: 'GET', params })
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
  return request<T>({ ...config, url, method: 'POST', data })
}

export function del<T = unknown>(url: string, config?: AxiosRequestConfig) {
  return request<T>({ ...config, url, method: 'DELETE' })
}

export function put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
  return request<T>({ ...config, url, method: 'PUT', data })
}

export default service
