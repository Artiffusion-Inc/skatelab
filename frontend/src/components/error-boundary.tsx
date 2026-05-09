"use client"

import { Button } from "@/components/ui/button"
import { AlertCircle } from "lucide-react"
import type { ReactNode } from "react"
import React from "react"

const getSentry = () => import("@sentry/nextjs").then(m => m)

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
  resetKey: number
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, resetKey: 0 }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, resetKey: 0 }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    getSentry().then(Sentry =>
      Sentry.captureException(error, {
        contexts: { react: { componentStack: errorInfo.componentStack } },
      })
    )
  }

  handleReset = () => {
    this.setState(prev => ({
      hasError: false,
      error: undefined,
      resetKey: prev.resetKey + 1,
    }))
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex min-h-[dvh] items-center justify-center p-4">
          <div className="mx-auto max-w-md p-8 text-center">
            <div className="mb-4 flex justify-center">
              <AlertCircle className="text-destructive size-12" />
            </div>
            <h2 className="sh-heading-lg mb-2 text-destructive">Something went wrong</h2>
            <p className="text-ink-mute mb-6 text-sm">
              {this.state.error?.message ?? "An unexpected error occurred."}
            </p>
            <Button onClick={this.handleReset} variant="default" className="bg-primary">
              Try again
            </Button>
          </div>
        </div>
      )
    }

    return <React.Fragment key={this.state.resetKey}>{this.props.children}</React.Fragment>
  }
}
