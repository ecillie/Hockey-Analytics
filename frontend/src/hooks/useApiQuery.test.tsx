import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useApiQuery } from './useApiQuery'

describe('useApiQuery', () => {
  it('loads data and retries', async () => {
    const loader = vi.fn().mockResolvedValueOnce('first').mockResolvedValueOnce('second')
    const { result } = renderHook(() => useApiQuery(loader, []))
    await waitFor(() => expect(result.current.data).toBe('first'))
    act(() => result.current.retry())
    await waitFor(() => expect(result.current.data).toBe('second'))
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('normalizes non-Error failures', async () => {
    const { result } = renderHook(() => useApiQuery(() => Promise.reject('bad'), []))
    await waitFor(() => expect(result.current.error?.message).toBe('Unknown error'))
    expect(result.current.loading).toBe(false)
  })

  it('retains Error failures and aborts on cleanup', async () => {
    const failure = new Error('failed')
    let capturedSignal: AbortSignal | undefined
    const { result, unmount } = renderHook(() => useApiQuery((signal) => {
      capturedSignal = signal
      return Promise.reject(failure)
    }, []))
    await waitFor(() => expect(result.current.error).toBe(failure))
    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })

  it('ignores fulfillment after unmount', async () => {
    let resolve!: (value: string) => void
    const promise = new Promise<string>((done) => { resolve = done })
    const { unmount } = renderHook(() => useApiQuery(() => promise, []))
    unmount()
    await act(async () => resolve('late'))
  })
})
