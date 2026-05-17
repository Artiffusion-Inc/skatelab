interface QueryLike {
  status: "pending" | "error" | "success"
  error?: Error | null
  data?: unknown
}

interface PageStatus {
  isLoading: boolean
  isError: boolean
  isFirstLoad: boolean
  error: Error | null
}

/**
 * Aggregate multiple React Query statuses into a single page-level status.
 *
 * - isLoading: any query is pending
 * - isError: any query has error
 * - isFirstLoad: any query is pending AND has never succeeded (no cached data)
 * - error: first error found
 */
export function usePageStatus(queries: QueryLike[]): PageStatus {
  const isLoading = queries.some(q => q.status === "pending")
  const isError = queries.some(q => q.status === "error")
  const firstError = queries.find(q => q.status === "error")?.error ?? null
  const isFirstLoad = queries.some(q => q.status === "pending" && q.data === undefined)

  return {
    isLoading,
    isError,
    isFirstLoad,
    error: firstError instanceof Error ? firstError : null,
  }
}
