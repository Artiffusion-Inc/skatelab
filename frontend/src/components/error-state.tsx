"use client"

import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
}

export function ErrorState({ title, message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12 text-center" role="alert">
      <AlertTriangle className="h-10 w-10 text-muted-foreground" />
      <div>
        <h3 className="text-lg font-medium">{title ?? "Что-то пошло не так"}</h3>
        {message && <p className="mt-1 text-sm text-muted-foreground">{message}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Попробовать снова
        </Button>
      )}
    </div>
  )
}
