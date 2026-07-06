/**
 * RED→GREEN repro tests for issues #820–#828 (frontend lib audit).
 *
 * #820 zip-parser multi-video zip nondeterministic (last-wins)
 * #821 zip-parser any .json overwrites manifest
 * #822 isVideoFile accepts .mkv but parseZip + render reject it
 * #823 compressVideoFFmpeg always upscales; WebCodecs does not
 * #824 COMPRESSION_TIMEOUT_MS exported but never used (dead export)
 * #825 apiFetch reads body.detail; backend ErrorResponse has no detail key
 * #826 logout() never checks res.ok — silent server session leak
 * #827 verifyEmail/resendVerification raw fetch — no 401 silent refresh
 * #828 authFetch 401 retry returns retry Response without checking retryRes.ok
 */

import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { zipSync, strToU8 } from "fflate"
import { parseZip, isVideoFile } from "../zip-parser"

const LIB_DIR = join(__dirname, "..")

function readSrc(name: string): string {
  return readFileSync(join(LIB_DIR, name), "utf-8")
}

function createTestZip(files: { name: string; content: string | Uint8Array }[]): File {
  const entries: Record<string, Uint8Array> = {}
  for (const f of files) {
    entries[f.name] = typeof f.content === "string" ? strToU8(f.content) : f.content
  }
  const zipped = zipSync(entries)
  return new File([zipped as BlobPart], "test.zip", { type: "application/zip" })
}

// ---------------------------------------------------------------------------
// #820: multi-video zip must pick deterministically (largest by bytes)
// ---------------------------------------------------------------------------

describe("#820 zip-parser multi-video deterministic", () => {
  it("picks the larger video regardless of central directory order", async () => {
    const big = new Uint8Array(100)
    const small = new Uint8Array(10)
    // small first in insertion order — must still pick big
    const zipA = createTestZip([
      { name: "small.mp4", content: small },
      { name: "big.mp4", content: big },
    ])
    const resA = await parseZip(zipA)
    expect(resA.videoName).toBe("big.mp4")
    expect(resA.video?.size).toBe(100)

    // reverse insertion order — same result (deterministic, not positional)
    const zipB = createTestZip([
      { name: "big.mp4", content: big },
      { name: "small.mp4", content: small },
    ])
    const resB = await parseZip(zipB)
    expect(resB.videoName).toBe("big.mp4")
  })

  it("does not let a corrupt second take silently shadow a good first take", async () => {
    const good = new Uint8Array(18)
    const broken = new Uint8Array(2)
    const zip = createTestZip([
      { name: "good_take.mp4", content: good },
      { name: "broken_take.mp4", content: broken },
    ])
    const res = await parseZip(zip)
    expect(res.videoName).toBe("good_take.mp4")
    expect(res.video?.size).toBe(18)
  })
})

// ---------------------------------------------------------------------------
// #821: manifest.json preferred; junk json does not overwrite
// ---------------------------------------------------------------------------

describe("#821 zip-parser manifest discrimination", () => {
  it("manifest.json wins over camera_metadata.json regardless of order", async () => {
    const zip = createTestZip([
      { name: "manifest.json", content: JSON.stringify({ version: "1.0", real: true }) },
      { name: "camera_metadata.json", content: JSON.stringify({ version: "9.9", iso: 800 }) },
    ])
    const res = await parseZip(zip)
    expect(res.manifestVersion).toBe("1.0")
    expect((res.manifest as Record<string, unknown>).real).toBe(true)
  })

  it("junk json without a string version does not overwrite a real manifest", async () => {
    const zip = createTestZip([
      { name: "manifest.json", content: JSON.stringify({ version: "1.0", real: true }) },
      { name: "junk.json", content: JSON.stringify({ unrelated: true }) },
    ])
    const res = await parseZip(zip)
    expect(res.manifestVersion).toBe("1.0")
    expect((res.manifest as Record<string, unknown>).real).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// #822: isVideoFile and parseZip agree on extensions (no mkv)
// ---------------------------------------------------------------------------

describe("#822 video extension gate agreement", () => {
  it("isVideoFile rejects .mkv (Matroska unsupported downstream)", () => {
    expect(isVideoFile(new File([], "take.mkv"))).toBe(false)
  })

  it("parseZip does not pick up .mkv as video", async () => {
    const zip = createTestZip([
      { name: "take.mkv", content: new Uint8Array([1, 2, 3]) },
      { name: "manifest.json", content: JSON.stringify({ version: "1.0" }) },
    ])
    const res = await parseZip(zip)
    expect(res.video).toBeNull()
    expect(res.videoName).toBeNull()
  })

  it("source has no mkv in the accepted video extension set", () => {
    const src = readSrc("zip-parser.ts")
    // No standalone "mkv" mention in accepted extensions (comment about
    // removal is fine — it must NOT be in an active allow-list literal).
    // The active VIDEO_EXTENSIONS constant must not include mkv.
    expect(src).toMatch(/VIDEO_EXTENSIONS\s*=\s*\[["']mp4["'],\s*["']mov["'],\s*["']webm["']\]/)
  })
})

// ---------------------------------------------------------------------------
// #823: ffmpeg path must not upscale small videos
// ---------------------------------------------------------------------------

describe("#823 ffmpeg upscale parity with WebCodecs", () => {
  it("source computes a scale capped at 1 (no unconditional maxWidth)", () => {
    const src = readSrc("video-compression.ts")
    const ffmpegBlockStart = src.indexOf("export async function compressVideoFFmpeg")
    expect(ffmpegBlockStart).toBeGreaterThan(-1)
    const block = src.slice(ffmpegBlockStart)
    // Must NOT use the old unconditional `scale=${options.maxWidth}:-2`
    expect(block).not.toMatch(/["'`]scale=\$\{options\.maxWidth\}:-2["'`]/)
    // Must reference a scale cap (Math.min with 1) or min(iw, maxWidth)
    expect(block).toMatch(/Math\.min\([^)]*,\s*1\)|min\(\$\{options\.maxWidth\},\s*iw\)/)
  })
})

// ---------------------------------------------------------------------------
// #824: COMPRESSION_TIMEOUT_MS must be referenced (timeout enforced)
// ---------------------------------------------------------------------------

describe("#824 compression timeout enforced", () => {
  it("COMPRESSION_TIMEOUT_MS is referenced in both compression functions", () => {
    const src = readSrc("video-compression.ts")
    const wcStart = src.indexOf("export async function compressVideoWebCodecs")
    const wcEnd = src.indexOf("export async function compressVideoFFmpeg")
    const wcBlock = src.slice(wcStart, wcEnd)
    expect(wcBlock).toContain("COMPRESSION_TIMEOUT_MS")

    // compressVideoFFmpeg block ends at the next top-level "Auto-select" comment
    const ffStart = src.indexOf("export async function compressVideoFFmpeg")
    const ffEnd = src.indexOf("Auto-select best compression method")
    const ffBlock = src.slice(ffStart, ffEnd === -1 ? undefined : ffEnd)
    expect(ffBlock).toContain("COMPRESSION_TIMEOUT_MS")
  })

  it("both paths use Promise.race with a timeout", () => {
    const src = readSrc("video-compression.ts")
    // At least two Promise.race calls (one per path)
    const races = src.match(/Promise\.race/g) ?? []
    expect(races.length).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// #825: apiFetch reads message/error, not body.detail
// ---------------------------------------------------------------------------

describe("#825 apiFetch error message shape", () => {
  it("api-client no longer reads body.detail as primary", () => {
    const src = readSrc("api-client.ts")
    // The old pattern `body.detail` passed to ApiError must be gone
    expect(src).not.toMatch(/new ApiError\(body\.detail/)
  })

  it("api-client has a helper that reads message then error then detail", () => {
    const src = readSrc("api-client.ts")
    expect(src).toMatch(/readErrorMessage|function\s+readErrorMessage/)
    // Must check message and error keys (backend ErrorResponse shape)
    expect(src).toMatch(/b\.message/)
    expect(src).toMatch(/b\.error/)
  })
})

// ---------------------------------------------------------------------------
// #826: logout checks res.ok / uses authFetch (no silent swallow)
// ---------------------------------------------------------------------------

describe("#826 logout surfaces server errors", () => {
  it("auth.ts logout uses authFetch and checks res.ok (no bare .catch swallow)", () => {
    const src = readSrc("auth.ts")
    const start = src.indexOf("export async function logout")
    const end = src.indexOf("export async function fetchMe")
    const block = src.slice(start, end)
    // Must use authFetch, not raw fetch
    expect(block).toMatch(/authFetch\(["']\/auth\/logout["']/)
    // Must check res.ok
    expect(block).toContain("res.ok")
    // Must NOT be a bare `.catch(() => {})` swallowing everything
    expect(block).not.toMatch(/\.catch\(\(\)\s*=>\s*\{\}\)/)
  })
})

// ---------------------------------------------------------------------------
// #827: verifyEmail/resendVerification use apiFetch (silent refresh)
// ---------------------------------------------------------------------------

describe("#827 verify/resend use apiFetch", () => {
  it("verifyEmail uses apiFetch, not raw fetch", () => {
    const src = readSrc("auth.ts")
    const start = src.indexOf("export async function verifyEmail")
    const end = src.indexOf("export async function resendVerification")
    const block = src.slice(start, end)
    expect(block).toMatch(/apiFetch\(["']\/auth\/verify-email["']/)
    expect(block).not.toMatch(/^\s*const res = await fetch\(/m)
  })

  it("resendVerification uses apiFetch, not raw fetch", () => {
    const src = readSrc("auth.ts")
    const start = src.indexOf("export async function resendVerification")
    const block = src.slice(start)
    expect(block).toMatch(/apiFetch\(["']\/auth\/resend-verification["']/)
  })
})

// ---------------------------------------------------------------------------
// #828: authFetch retry checks retryRes.ok (401 again → handleAuthFailure)
// ---------------------------------------------------------------------------

describe("#828 authFetch retry validates retry response", () => {
  it("authFetch handles a 401 on retry (does not return 401 as ok)", () => {
    const src = readSrc("api-client.ts")
    const start = src.indexOf("export async function authFetch")
    const end = src.indexOf(
      "// ---------------------------------------------------------------------------\n// Convenience helpers",
    )
    const block = src.slice(start, end === -1 ? undefined : end)
    // Must check retry response status for 401 and call handleAuthFailure
    expect(block).toMatch(/retryRes\.status\s*===\s*401/)
    expect(block).toMatch(/handleAuthFailure\(\)/)
  })
})
