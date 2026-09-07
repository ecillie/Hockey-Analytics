import type { ApiService } from './types'
import { httpApi } from './httpService'
import { mockApi } from '../mocks/mockApi'

export const isMockMode = import.meta.env.VITE_USE_MOCK_API !== 'false'
export const api: ApiService = isMockMode ? mockApi : httpApi
export * from './types'
export { ApiError, ApiClient } from './client'
