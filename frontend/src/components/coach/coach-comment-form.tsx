"use client"

import { useState } from "react"
import { useTranslations } from "@/i18n"
import { useCreateComment } from "@/lib/api/comments"
import { Button } from "@/components/ui/button"

const MAX_COMMENT_LENGTH = 2000

export function CoachCommentForm({ sessionId }: { sessionId: string }) {
  const t = useTranslations("session")
  const [content, setContent] = useState("")
  const [showSuccess, setShowSuccess] = useState(false)
  const mutation = useCreateComment()

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmedContent = content.trim()
    if (!trimmedContent || mutation.isPending) return

    setShowSuccess(false)
    mutation.mutate(
      { sessionId, content: trimmedContent },
      {
        onSuccess: () => {
          setContent("")
          setShowSuccess(true)
        },
      },
    )
  }

  return (
    <section
      className="rounded-2xl border border-hairline p-3 sm:p-4"
      aria-labelledby="comment-title"
    >
      <h2 id="comment-title" className="mb-3 text-sm font-medium">
        {t("coachCommentTitle")}
      </h2>
      <form onSubmit={handleSubmit} aria-busy={mutation.isPending}>
        <label htmlFor="coach-comment" className="sr-only">
          {t("commentLabel")}
        </label>
        <textarea
          id="coach-comment"
          name="content"
          value={content}
          onChange={event => {
            setContent(event.target.value)
            setShowSuccess(false)
          }}
          placeholder={t("commentPlaceholder")}
          maxLength={MAX_COMMENT_LENGTH}
          required
          rows={4}
          className="w-full resize-y rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm outline-none placeholder:text-ink-mute focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <span className="text-xs text-ink-mute">
            {t("commentCharacters", { count: content.length })}
          </span>
          <Button type="submit" size="lg" disabled={mutation.isPending || !content.trim()}>
            {mutation.isPending ? t("sendingComment") : t("sendComment")}
          </Button>
        </div>
      </form>
      {mutation.isError && !showSuccess && (
        <p className="mt-3 text-sm text-destructive" role="alert">
          {t("commentError")}
        </p>
      )}
      {showSuccess && (
        <p className="mt-3 text-sm text-ink-mute" role="status" aria-live="polite">
          {t("commentSent")}
        </p>
      )}
    </section>
  )
}
