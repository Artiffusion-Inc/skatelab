"use client"

import { useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { Loader2, CheckCircle2, X } from "lucide-react"
import { toast } from "sonner"
import { useTranslations } from "@/i18n"
import { useMountEffect } from "@/lib/useMountEffect"
import { ChunkedUploader, presignUpload, uploadToPresignedUrl } from "@/lib/api/uploads"
import { useCreateSession, usePatchSession } from "@/lib/api/sessions"
import { enqueueProcess } from "@/lib/api/process"
import { parseZip, isZipFile, type ZipContents } from "@/lib/zip-parser"
import { DropZone } from "@/components/upload/drop-zone"
import { FilePreview } from "@/components/upload/file-preview"
import { useVideoCompression, type CompressionState } from "@/lib/use-video-compression"
import { shouldCompress } from "@/lib/video-compression"

type Step = "idle" | "parsing" | "picked" | "compressing" | "uploading" | "done"

export default function UploadPage() {
  const router = useRouter()
  const createSession = useCreateSession()
  const patchSession = usePatchSession()
  const t = useTranslations("upload")

  const [step, setStep] = useState<Step>("idle")
  const [file, setFile] = useState<File | null>(null)
  const [zipContents, setZipContents] = useState<ZipContents | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [uploadPhase, setUploadPhase] = useState("")
  const uploaderRef = useRef<ChunkedUploader | null>(null)
  const { state: compressionState, compress, abort: abortCompression } = useVideoCompression()

  useMountEffect(() => {
    return () => {
      uploaderRef.current?.abort()
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  })

  async function handleFile(f: File) {
    if (isZipFile(f)) {
      setStep("parsing")
      try {
        const contents = await parseZip(f)
        if (!contents.video) {
          toast.error(t("noVideoInZip"))
          setStep("idle")
          return
        }
        setFile(f)
        setZipContents(contents)
        setStep("picked")
      } catch {
        toast.error(t("zipReadError"))
        setStep("idle")
      }
    } else {
      setFile(f)
      setZipContents(null)
      setPreviewUrl(URL.createObjectURL(f))
      setStep("picked")
    }
  }

  function handleRemove() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(null)
    setZipContents(null)
    setPreviewUrl(null)
    setProgress(0)
    setStep("idle")
  }

  async function uploadToR2(
    data: Blob | ArrayBuffer,
    fileName: string,
    contentType: string,
  ): Promise<string> {
    const { url, key } = await presignUpload(fileName, contentType)
    await uploadToPresignedUrl(url, data, contentType)
    return key
  }

  async function handleUpload() {
    if (!file) return
    setStep("compressing")
    setProgress(0)

    try {
      // Phase 0: Compress video before upload
      // Extract video from ZIP if needed, then compress if > 10 MB
      const videoFile = zipContents?.video ?? file

      let compressedFile: File = videoFile
      if (shouldCompress(videoFile)) {
        try {
          const result = await Promise.race([
            compress(videoFile),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error("Compression timeout")), 60_000),
            ),
          ])
          compressedFile = new File([result.blob], "compressed.mp4", { type: "video/mp4" })
          toast.success(
            t("compressionDone", {
              original: `${(result.originalSize / 1e6).toFixed(1)} MB`,
              compressed: `${(result.compressedSize / 1e6).toFixed(1)} MB`,
            }),
          )
        } catch {
          // Timeout or error — skip compression, upload original
          toast.info(t("compressionSkip"))
        }
      }

      setStep("uploading")
      setProgress(0)

      let imuLeftKey: string | null = null
      let imuRightKey: string | null = null
      let manifestKey: string | null = null

      // Phase 1: Upload IMU/manifest to R2 via presigned URLs (if ZIP)
      if (zipContents) {
        setUploadPhase(t("uploadingImu"))

        if (zipContents.imuLeft) {
          imuLeftKey = await uploadToR2(
            new Blob([new Uint8Array(zipContents.imuLeft)]),
            "imu_left.pb",
            "application/x-protobuf",
          )
        }
        if (zipContents.imuRight) {
          imuRightKey = await uploadToR2(
            new Blob([new Uint8Array(zipContents.imuRight)]),
            "imu_right.pb",
            "application/x-protobuf",
          )
        }
        if (zipContents.manifest) {
          const manifestData = new TextEncoder().encode(JSON.stringify(zipContents.manifest))
          manifestKey = await uploadToR2(
            new Blob([manifestData]),
            "manifest.json",
            "application/json",
          )
        }
      }

      // Phase 2: Upload compressed video via ChunkedUploader
      setUploadPhase(t("uploadingVideo"))
      const uploader = new ChunkedUploader(compressedFile, (loaded, total) => {
        setProgress(Math.round((loaded / total) * 100))
      })
      uploaderRef.current = uploader
      const videoKey = await uploader.upload()

      // Phase 3: Create session with ALL keys
      setUploadPhase(t("startingAnalysis"))
      setProgress(100)
      const session = await createSession.mutateAsync({
        element_type: "auto",
        video_key: videoKey,
        ...(imuLeftKey ? { imu_left_key: imuLeftKey } : {}),
        ...(imuRightKey ? { imu_right_key: imuRightKey } : {}),
        ...(manifestKey ? { manifest_key: manifestKey } : {}),
      })

      // Phase 4: Enqueue processing
      const processRes = await enqueueProcess({
        video_key: videoKey,
        person_click: { x: -1, y: -1 },
        session_id: session.id,
      })
      await patchSession.mutateAsync({
        id: session.id,
        body: { process_task_id: processRes.task_id },
      })

      setStep("done")
      toast.success(t("videoUploaded"))

      if (session?.id) {
        router.push(`/sessions/${session.id}`)
      }
    } catch {
      toast.error(t("uploadError"))
      setProgress(0)
      setStep("picked")
    }
  }

  function handleCancel() {
    uploaderRef.current?.abort()
    setProgress(0)
    setStep("picked")
  }

  if (step === "done") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 px-4 py-20">
        <CheckCircle2 className="h-12 w-12 text-primary" />
        <p className="sh-display-md">{t("videoUploaded")}</p>
        <p className="text-sm text-ink-mute">{t("analyzingHint")}</p>
        <Loader2 className="h-5 w-5 animate-spin text-ink-mute" />
      </div>
    )
  }

  if (step === "parsing") {
    return (
      <div className="mx-auto max-w-lg space-y-5 px-4 py-20">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
          <p className="mt-3 sh-display-md">{t("parsingZip")}</p>
        </div>
      </div>
    )
  }

  if (step === "compressing") {
    const percent = compressionState.status === "compressing" ? compressionState.percent : 0
    return (
      <div className="mx-auto max-w-lg space-y-5 px-4 py-20">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
          <p className="mt-3 sh-display-md">{t("compressing", { percent })}</p>
        </div>
        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => {
              abortCompression()
              setStep("picked")
            }}
            className="flex items-center gap-2 rounded-2xl border border-hairline px-4 py-2 text-sm text-ink-mute transition-colors hover:bg-accent"
          >
            <X className="h-4 w-4" />
            {t("cancelUpload")}
          </button>
        </div>
      </div>
    )
  }

  if (step === "uploading") {
    return (
      <div className="mx-auto max-w-lg space-y-5 px-4 py-20">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
          <p className="mt-3 sh-display-md">{uploadPhase}</p>
        </div>
        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-center text-xs text-ink-mute">{progress}%</p>
        </div>
        <div className="flex justify-center">
          <button
            type="button"
            onClick={handleCancel}
            className="flex items-center gap-2 rounded-2xl border border-hairline px-4 py-2 text-sm text-ink-mute transition-colors hover:bg-accent"
          >
            <X className="h-4 w-4" />
            {t("cancelUpload")}
          </button>
        </div>
      </div>
    )
  }

  if (step === "picked" && file) {
    return (
      <FilePreview
        file={file}
        zipContents={zipContents}
        previewUrl={previewUrl}
        onRemove={handleRemove}
        onUpload={handleUpload}
      />
    )
  }

  return (
    <div className="flex flex-col items-center justify-center gap-4 px-4 py-8">
      <DropZone
        onFile={handleFile}
        invalidFile={t("invalidFile")}
        fileTooLarge={t("fileTooLarge")}
      />
    </div>
  )
}