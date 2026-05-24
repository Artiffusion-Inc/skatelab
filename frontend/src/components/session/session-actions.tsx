"use client"

import { useRouter } from "next/navigation"
import { Share2, Trash2 } from "lucide-react"
import { useTranslations } from "@/i18n"
import { useDeleteSession } from "@/lib/api/sessions"
import { captureEvent } from "@/lib/posthog"

interface Props {
  sessionId: string
}

export function SessionActions({ sessionId }: Props) {
  const t = useTranslations("session")
  const router = useRouter()
  const deleteMutation = useDeleteSession()

  const handleShare = async () => {
    const url = typeof document !== "undefined" ? document.URL : ""
    await navigator.clipboard.writeText(url)
    captureEvent("social_share_clicked", {
      platform: "clipboard",
      content_type: "session_result",
    })
  }

  const handleDelete = () => {
    if (!window.confirm(t("deleteConfirm"))) return
    deleteMutation.mutate(sessionId, {
      onSuccess: () => router.push("/feed"),
    })
  }

  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={handleShare}
        className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-sm hover:bg-muted"
      >
        <Share2 className="h-4 w-4" />
        {t("share")}
      </button>
      <button
        type="button"
        onClick={handleDelete}
        disabled={deleteMutation.isPending}
        className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
      >
        <Trash2 className="h-4 w-4" />
        {deleteMutation.isPending ? t("deleting") : t("delete")}
      </button>
    </div>
  )
}
