import type { ApiErrorBody } from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details?: Record<string, string[]>,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type QueryValue = string | number | boolean | null | undefined | Array<string | number>

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  async get<T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal): Promise<T> {
    const url = new URL(path, this.baseUrl.endsWith('/') ? this.baseUrl : `${this.baseUrl}/`)
    Object.entries(query ?? {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      url.searchParams.set(key, Array.isArray(value) ? value.join(',') : String(value))
    })

    let response: Response
    try {
      response = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, signal })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error
      throw new ApiError('Unable to reach the NHL Statistics API.', 0, 'NETWORK_ERROR')
    }

    const contentType = response.headers.get('content-type') ?? ''
    const body: unknown = contentType.includes('application/json') ? await response.json() : null
    if (!response.ok) {
      const apiBody = body as Partial<ApiErrorBody> | null
      throw new ApiError(
        apiBody?.error?.message ?? 'The API could not complete this request.',
        response.status,
        apiBody?.error?.code ?? `HTTP_${response.status}`,
        apiBody?.error?.details,
      )
    }
    if (!contentType.includes('application/json')) throw new ApiError('The API returned an invalid response.', response.status, 'INVALID_RESPONSE')
    return body as T
  }
}
