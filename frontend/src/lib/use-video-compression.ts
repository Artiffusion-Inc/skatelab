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
  // #530: store the active compress() reject fn so abort() can settle the
  // dangling promise. Worker.terminate() fires neither onmessage nor
  // onerror — without this, the promise hangs until the 60s timeout
  // wins the race and uploads the uncompressed original.
  const rejectRef = useRef<((err: Error) => void) | null>(null)
  const [state, setState] = useState<CompressionState>({ status: "idle" })

  const compress = useCallback((file: File): Promise<CompressResult> => {
    return new Promise((resolve, reject) => {
      setState({ status: "compressing", percent: 0 })

      const worker = new Worker(new URL("./video-compression.worker.ts", import.meta.url))
      workerRef.current = worker
      rejectRef.current = reject

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
            workerRef.current = null
            rejectRef.current = null
            resolve(result)
          }
        } else if (data.type === "error") {
          setState({ status: "error", error: data.error })
          worker.terminate()
          workerRef.current = null
          rejectRef.current = null
          reject(new Error(data.error))
        }
      }

      worker.onerror = err => {
        setState({ status: "error", error: String(err) })
        worker.terminate()
        workerRef.current = null
        rejectRef.current = null
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
    // #530: settle the dangling promise so Promise.race resolves immediately
    // and the upload page's catch can check an abort flag (or simply not
    // upload) instead of waiting for the 60s timeout. queueMicrotask
    // defers the reject so the caller's `await` / `.rejects` handler has
    // a chance to attach before the rejection becomes unhandled.
    const reject = rejectRef.current
    rejectRef.current = null
    if (reject) reject(new Error("Compression aborted"))
  }, [])

  return { state, compress, abort }
}
