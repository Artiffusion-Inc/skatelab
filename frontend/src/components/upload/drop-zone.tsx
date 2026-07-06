"use client"

import { useCallback, useRef, useState } from "react"
import { Upload } from "lucide-react"
import { toast } from "sonner"
import { useTranslations } from "@/i18n"
import { isZipFile, isVideoFile } from "@/lib/zip-parser"

// #822: drop .mkv — parseZip and the render/compression path don't support
// Matroska. Keep the upload gate's accept list in sync with VIDEO_EXTENSIONS
// in zip-parser.ts (mp4/mov/webm).
const ACCEPTED_EXTENSIONS = ".zip,.mp4,.mov,.webm"
// #830: gate used to check the *pre-compression* file.size against a 50 MB
// cap labeled "(compressed)". The upload pipeline (upload/page.tsx) runs
// compressVideo first — 6-10x reduction — so a 200 MB raw clip that compresses
// to ~25 MB was rejected at the gate while the pipeline would have handled it.
// Raise to a realistic pre-compression ceiling. Compression still runs after,
// and the *compressed* upload is what the backend sees.
const MAX_SIZE = 500 * 1024 * 1024 // 500MB pre-compression

export function DropZone({
  onFile,
  invalidFile,
  fileTooLarge,
}: {
  onFile: (file: File) => void
  invalidFile: string
  fileTooLarge: string
}) {
  const t = useTranslations("upload")
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const validate = useCallback(
    (file: File): boolean => {
      if (!isZipFile(file) && !isVideoFile(file)) {
        toast.error(invalidFile)
        return false
      }
      if (file.size > MAX_SIZE) {
        toast.error(fileTooLarge)
        return false
      }
      return true
    },
    [invalidFile, fileTooLarge],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file && validate(file)) onFile(file)
    },
    [onFile, validate],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file && validate(file)) onFile(file)
    },
    [onFile, validate],
  )

  return (
    /* biome-ignore lint/a11y/useSemanticElements: drop zone needs div for drag events */
    <div
      role="button"
      tabIndex={0}
      onDragOver={e => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click()
      }}
      className={`mx-auto flex max-w-lg cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-8 py-16 transition-colors ${
        dragOver
          ? "border-primary bg-primary/5"
          : "border-hairline hover:border-primary/50 hover:bg-accent/30"
      }`}
    >
      <Upload className="h-10 w-10 text-ink-mute" />
      <p className="sh-display-md">{t("dropHint")}</p>
      <p className="text-sm text-ink-mute">{t("dropOrClick")}</p>
      <p className="text-xs text-ink-mute">{t("maxSize")}</p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        className="hidden"
        onChange={handleChange}
      />
    </div>
  )
}
