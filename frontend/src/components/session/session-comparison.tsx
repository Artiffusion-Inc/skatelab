"use client"

import { useState } from "react"
import { useLocale, useTranslations } from "@/i18n"
import { useSession, useSessions } from "@/lib/api/sessions"
import { VideoWithSkeleton } from "@/components/analysis/video-with-skeleton"

export function SessionComparison() {
  const t = useTranslations("compare")
  const locale = useLocale()
  const { data: sessionsData } = useSessions()
  const [leftId, setLeftId] = useState("")
  const [rightId, setRightId] = useState("")
  const { data: leftSession } = useSession(leftId)
  const { data: rightSession } = useSession(rightId)

  const sessions = sessionsData?.sessions ?? []

  const leftTotalFrames = leftSession?.pose_data ? Math.max(...leftSession.pose_data.frames) : 300
  const rightTotalFrames = rightSession?.pose_data
    ? Math.max(...rightSession.pose_data.frames)
    : 300

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:gap-4">
        <select
          value={leftId}
          onChange={e => setLeftId(e.target.value)}
          className="flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-sm"
        >
          <option value="">{t("selectLeft")}</option>
          {sessions.map(s => (
            <option key={s.id} value={s.id}>
              {s.element_type} — {new Date(s.created_at).toLocaleDateString(locale)}
            </option>
          ))}
        </select>
        <select
          value={rightId}
          onChange={e => setRightId(e.target.value)}
          className="flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-sm"
        >
          <option value="">{t("selectRight")}</option>
          {sessions.map(s => (
            <option key={s.id} value={s.id}>
              {s.element_type} — {new Date(s.created_at).toLocaleDateString(locale)}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {leftSession?.pose_data && leftSession?.processed_video_url && (
          <VideoWithSkeleton
            videoUrl={leftSession.processed_video_url}
            poseData={leftSession.pose_data}
            phases={leftSession.phases ?? null}
            totalFrames={leftTotalFrames}
            fps={leftSession.pose_data.fps}
            className="rounded-xl"
          />
        )}
        {rightSession?.pose_data && rightSession?.processed_video_url && (
          <VideoWithSkeleton
            videoUrl={rightSession.processed_video_url}
            poseData={rightSession.pose_data}
            phases={rightSession.phases ?? null}
            totalFrames={rightTotalFrames}
            fps={rightSession.pose_data.fps}
            className="rounded-xl"
          />
        )}
      </div>
    </div>
  )
}
