"use client"

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ThemeProvider } from "next-themes"
import { type ReactNode, useState } from "react"
import { AuthProvider } from "@/components/auth-provider"
import { ErrorBoundary } from "@/components/error-boundary"
import { ApiError } from "@/lib/api-client"

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError(error) {
            if (
              error instanceof ApiError &&
              error.status === 401 &&
              typeof window !== "undefined"
            ) {
              const path = globalThis.location.pathname
              const isPublic =
                path === "/" || path.startsWith("/login") || path.startsWith("/register")
              if (!isPublic) globalThis.location.href = "/login"
            }
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            retry: (failureCount, error) => {
              if (error instanceof ApiError && error.status === 401) return false
              return failureCount < 1
            },
            refetchOnWindowFocus: false,
          },
        },
      }),
  )

  return (
    <ThemeProvider attribute="class" forcedTheme="light" disableTransitionOnChange>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>{children}</AuthProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </ThemeProvider>
  )
}
