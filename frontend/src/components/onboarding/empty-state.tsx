"use client"

import Link from "next/link"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description: string
  primaryAction?: {
    label: string
    href: string
  }
  secondaryAction?: {
    label: string
    href: string
    onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void
  }
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex flex-col items-center justify-center py-20 px-4 text-center", className)}
    >
      {icon && (
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-[1.25rem] bg-primary/5 text-primary">
          {icon}
        </div>
      )}
      <h3 className="mb-2 text-lg font-medium text-foreground">{title}</h3>
      <p className="mb-8 max-w-sm text-sm text-ink-mute leading-relaxed">{description}</p>

      <div className="flex flex-col items-center gap-3 sm:flex-row">
        {primaryAction && (
          <Link
            href={primaryAction.href}
            className="inline-flex h-11 items-center justify-center rounded-md px-8 text-sm font-bold text-primary-foreground transition-all duration-200 bg-primary hover:scale-[0.98] active:scale-[0.96]"
          >
            {primaryAction.label}
          </Link>
        )}
        {secondaryAction && (
          <Link
            href={secondaryAction.href}
            onClick={secondaryAction.onClick}
            className="inline-flex min-h-[44px] items-center px-3 text-sm font-medium text-ink-mute hover:text-foreground transition-colors"
          >
            {secondaryAction.label}
          </Link>
        )}
      </div>
    </div>
  )
}
