"use client"

import { useRef, useCallback, useState } from "react"
import type { CompressResult } from "./video-compression"

export type CompressionState =
  | { status: "idle" }
  | { status: "compressing"; percent: number }
  | { status: "done"; result: CompressResult }
  | { status: "error"; error: string }

export function useVideoCompression() {
  const workerRef = useRef<Worker | null>(null)
  const [state, setState] = useState<CompressionState>({ status: "idle" })

  const compress = useCallback((file: File): Promise<CompressResult> => {
    return new Promise((resolve, reject) => {
      setState({ status: "compressing", percent: 0 })

      const worker = new Worker(new URL("./video-compression.worker.ts", import.meta.url))
      workerRef.current = worker

      let resultBlob: Blob | null = null
      let resultMeta: { originalSize: number; compressedSize: number } | null = null

      worker.onmessage = e => {
        const data = e.data
        if (data.type === "progress") {
          setState({ status: "compressing", percent: data.percent })
        } else if (data.type === "result") {
          resultMeta = data.result
        } else if (data.type === "blob") {
          resultBlob = data.blob
          if (resultMeta && resultBlob) {
            const result: CompressResult = {
              blob: resultBlob,
              originalSize: resultMeta.originalSize,
              compressedSize: resultMeta.compressedSize,
            }
            setState({ status: "done", result })
            worker.terminate()
            resolve(result)
          }
        } else if (data.type === "error") {
          setState({ status: "error", error: data.error })
          worker.terminate()
          reject(new Error(data.error))
        }
      }

      worker.onerror = err => {
        setState({ status: "error", error: String(err) })
        worker.terminate()
        reject(err)
      }

      worker.postMessage({
        type: "compress",
        file,
        options: { maxWidth: 1280, maxHeight: 720, fps: 30, bitrate: 2_000_000 },
      })
    })
  }, [])

  const abort = useCallback(() => {
    workerRef.current?.terminate()
    workerRef.current = null
    setState({ status: "idle" })
  }, [])

  return { state, compress, abort }
}
