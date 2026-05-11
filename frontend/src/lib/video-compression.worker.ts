/**
 * Web Worker for video compression — keeps UI thread responsive.
 * Posts progress updates and the compressed Blob back to main thread.
 */
import { compressVideo, type CompressOptions, type CompressResult } from "./video-compression"

interface WorkerMessage {
  type: "compress"
  file: File
  options: CompressOptions
}

interface WorkerResponse {
  type: "progress" | "result" | "error"
  percent?: number
  result?: { originalSize: number; compressedSize: number }
  error?: string
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  if (e.data.type !== "compress") return

  const { file, options } = e.data

  const respond = (msg: WorkerResponse) => self.postMessage(msg)

  try {
    const result = await compressVideo(file, {
      ...options,
      onProgress: percent => respond({ type: "progress", percent }),
    })

    respond({
      type: "result",
      result: {
        originalSize: result.originalSize,
        compressedSize: result.compressedSize,
      },
    })

    // Send blob separately as transferable
    self.postMessage({ type: "blob", blob: result.blob } as { type: "blob"; blob: Blob })
  } catch (err) {
    respond({ type: "error", error: String(err) })
  }
}
