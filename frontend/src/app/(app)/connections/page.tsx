"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Users } from "lucide-react"
import { useTranslations } from "@/i18n"
import { EmptyState } from "@/components/onboarding"
import { ErrorState } from "@/components/error-state"
import { SkeletonConnection } from "@/components/skeleton-connection"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import {
  useAcceptConnection,
  useConnections,
  useEndConnection,
  useInviteConnection,
  usePendingConnections,
} from "@/lib/api/connections"

export default function ConnectionsPage() {
  const connsQuery = useConnections()
  const pendingQuery = usePendingConnections()
  const invite = useInviteConnection()
  const acceptConn = useAcceptConnection()
  const endConn = useEndConnection()
  const t = useTranslations("toast")
  const tc = useTranslations("connections")
  const tEmpty = useTranslations("emptyStates")

  const { isFirstLoad, isError } = usePageStatus([connsQuery, pendingQuery])

  const [email, setEmail] = useState("")

  const handleInvite = async () => {
    if (!email) return
    try {
      await invite.mutateAsync({ to_user_email: email, connection_type: "coaching" })
      toast.success(t("invitationSent"))
      setEmail("")
    } catch {
      toast.error(t("inviteSendError"))
    }
  }

  // #496: accept/end connection handlers — same try/catch + toast.error
  // pattern as handleInvite. Pre-fix: bare `mutateAsync` calls rejected
  // on API failure → unhandled promise rejection + no user-visible
  // feedback. Post-fix: same pattern as handleInvite for consistency
  // (the user sees a toast on every error path).
  const handleAccept = async (connId: string) => {
    try {
      await acceptConn.mutateAsync(connId)
    } catch {
      toast.error(t("inviteSendError"))
    }
  }

  const handleEnd = async (connId: string) => {
    try {
      await endConn.mutateAsync(connId)
    } catch {
      toast.error(t("inviteSendError"))
    }
  }

  if (isFirstLoad)
    return (
      <div className="mx-auto max-w-2xl sm:max-w-3xl">
        <SkeletonConnection />
      </div>
    )
  if (isError)
    return (
      <ErrorState
        onRetry={() => {
          connsQuery.refetch()
          pendingQuery.refetch()
        }}
      />
    )

  const conns = connsQuery.data
  const pending = pendingQuery.data
  const activeConns = (conns?.connections ?? []).filter(r => r.status === "active")
  const hasPending = pending && pending.connections.length > 0
  const hasActive = activeConns.length > 0

  if (!hasPending && !hasActive) {
    return (
      <EmptyState
        icon={<Users className="h-7 w-7 text-primary" />}
        title={tEmpty("connectionsTitle")}
        description={tEmpty("connectionsDesc")}
        primaryAction={{ label: tEmpty("connectionsAction"), href: "#invite" }}
      />
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 sm:max-w-3xl">
      <h1 className="text-lg font-semibold">{tc("title")}</h1>

      <div id="invite" className="space-y-2">
        <p className="text-sm font-medium">{tc("inviteStudent")}</p>
        <div className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="email@example.com"
            className="flex-1 rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm"
          />
          <button
            type="button"
            onClick={handleInvite}
            className="whitespace-nowrap rounded-xl bg-primary text-primary-foreground px-4 py-2.5 text-sm"
          >
            {tc("invite")}
          </button>
        </div>
      </div>

      {hasPending && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{tc("incomingInvites")}</p>
          {pending.connections.map((r, i) => (
            <div
              key={r.id ?? `pending-${i}`}
              className="flex items-center justify-between rounded-xl border border-hairline p-3"
            >
              <span className="text-sm truncate mr-2">{r.from_user_name || r.from_user_id}</span>
              <button
                type="button"
                onClick={() => handleAccept(r.id)}
                className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground"
              >
                {tc("accept")}
              </button>
            </div>
          ))}
        </div>
      )}

      {hasActive && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{tc("activeConnections")}</p>
          {activeConns.map((r, i) => (
            <div
              key={r.id ?? `conn-${i}`}
              className="flex items-center justify-between rounded-xl border border-hairline p-3"
            >
              <span className="text-sm truncate mr-2">{r.to_user_name || r.to_user_id}</span>
              <button
                type="button"
                onClick={() => handleEnd(r.id)}
                className="shrink-0 text-xs text-ink-mute hover:text-destructive"
              >
                {tc("endConnection")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
