import { unzip, type Unzipped } from "fflate"

export interface ZipContents {
  video: File | null
  imuLeft: Uint8Array | null
  imuRight: Uint8Array | null
  manifest: { [key: string]: unknown } | null
  videoName: string | null
  manifestVersion: string | null
}

function unzipAsync(file: File): Promise<Unzipped> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      unzip(new Uint8Array(reader.result as ArrayBuffer), (err, data) => {
        if (err) reject(err)
        else resolve(data)
      })
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(file)
  })
}

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

// #822: single source of truth for accepted video extensions. Three gates
// (isVideoFile upload gate, parseZip, render/compression path) must agree.
// mkv dropped — Matroska not renderable by <video> in browser builds and
// compressVideoWebCodecs only probes Mp4/QuickTime input formats.
const VIDEO_EXTENSIONS = ["mp4", "mov", "webm"] as const
const VIDEO_EXT_SET = new Set<string>(VIDEO_EXTENSIONS)

export async function parseZip(file: File): Promise<ZipContents> {
  const entries = await unzipAsync(file)

  let video: File | null = null
  let videoName: string | null = null
  let imuLeft: Uint8Array | null = null
  let imuRight: Uint8Array | null = null
  let manifest: { [key: string]: unknown } | null = null
  let manifestVersion: string | null = null

  // #820: collect candidate videos, pick deterministically (largest by bytes).
  // Was: last-wins positional overwrite — nondeterministic, depended on
  // central directory order.
  const videoCandidates: { name: string; data: Uint8Array; ext: string }[] = []

  for (const [path, data] of Object.entries(entries)) {
    const name = basename(path)

    // Skip macOS metadata
    if (path.startsWith("__MACOSX") || name.startsWith(".")) continue

    const ext = name.split(".").pop()?.toLowerCase() ?? ""
    if (VIDEO_EXT_SET.has(ext)) {
      videoCandidates.push({ name, data, ext })
    } else if (name.endsWith("_left.pb")) {
      imuLeft = data
    } else if (name.endsWith("_right.pb")) {
      imuRight = data
    } else if (ext === "json") {
      // #821: prefer manifest.json; for other .json files, only accept them
      // when no manifest.json has been claimed yet AND the parsed object
      // looks like a manifest (string version field). Was: positional
      // last-wins — camera_metadata.json silently overwrote the real manifest.
      try {
        const parsed = JSON.parse(new TextDecoder().decode(data)) as { [key: string]: unknown }
        const looksLikeManifest = typeof parsed.version === "string"
        // manifest.json always wins; other json only fills if nothing claimed
        if (name === "manifest.json" || (manifest === null && looksLikeManifest)) {
          manifest = parsed
          manifestVersion = typeof parsed.version === "string" ? parsed.version : null
        }
      } catch {
        // Not a valid JSON manifest, skip
      }
    }
  }

  // #820: deterministic — largest video wins. Tie-break by name for stability.
  if (videoCandidates.length > 0) {
    videoCandidates.sort(
      (a, b) => b.data.byteLength - a.data.byteLength || a.name.localeCompare(b.name),
    )
    const pick = videoCandidates[0]
    const blob = new Blob([new Uint8Array(pick.data) as BlobPart], { type: `video/${pick.ext}` })
    video = new File([blob], pick.name, { type: `video/${pick.ext}` })
    videoName = pick.name
  }

  return { video, imuLeft, imuRight, manifest, videoName, manifestVersion }
}

export function isZipFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".zip") || file.type === "application/zip"
}

export function isVideoFile(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
  // #822: mkv removed — parseZip and render/compression path don't support
  // Matroska. All three gates now agree on the same extension set.
  if (VIDEO_EXT_SET.has(ext)) return true
  if (file.type.startsWith("video/")) return true
  return false
}
