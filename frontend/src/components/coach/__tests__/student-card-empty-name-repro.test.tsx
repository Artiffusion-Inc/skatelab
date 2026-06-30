/**
 * RED repro — StudentCard crashes (TypeError) on empty `to_user_name`.
 *
 * BUG #1 (MEDIUM-HIGH — coach dashboard breaks):
 *   frontend/src/components/coach/student-card.tsx:17
 *     const initial = (conn.to_user_name ?? "?")[0].toUpperCase()
 *
 *   `?? "?"` only catches null/undefined, NOT the empty string `""`.
 *   When `to_user_name === ""`:
 *     ("" ?? "?")[0]  →  ""[0]  →  undefined
 *     undefined.toUpperCase()  →  TypeError: undefined is not an object
 *   StudentCard render throws → the coach /dashboard list breaks for ANY coach
 *   who has even one student with an empty display_name.
 *
 * Reachability:
 *   backend/app/routes/connections.py:48
 *     to_user_name = conn.to_user.display_name if conn.to_user else None
 *   UpdateProfileRequest.display_name has max_length=100 but NO min_length=1 →
 *   a user can set display_name="" via the profile API.
 *   Frontend Zod (lib/api/connections.ts): to_user_name: z.string().nullable()
 *   accepts "". A coach viewing that student's connection card → crash.
 *
 *   Bug-class: empty-string-crash — falsy-but-not-nullish `??` misuse. `??`
 *   only guards null/undefined; `||` guards all falsy (incl "").
 *
 * This test asserts StudentCard does NOT throw on an empty to_user_name. It
 * currently throws TypeError → `expect(...).not.toThrow()` FAILS → RED.
 */

import { describe, expect, it } from "vitest"
import { render } from "@testing-library/react"
import type { Connection } from "@/types"
import { StudentCard } from "@/components/coach/student-card"

// Minimal valid Connection fixture — all fields StudentCard reads.
// StudentCard reads: to_user_id (Link href), to_user_name (initial + label),
// created_at (date). Other Connection fields are required by the type but not
// read by the component; populate them so the fixture type-checks.
function makeConn(overrides: Partial<Connection> = {}): Connection {
  return {
    id: "conn-1",
    from_user_id: "coach-1",
    to_user_id: "student-1",
    connection_type: "coaching",
    status: "active",
    initiated_by: "coach-1",
    created_at: "2026-06-29T10:00:00Z",
    ended_at: null,
    from_user_name: "Coach",
    to_user_name: "Alice",
    ...overrides,
  }
}

describe("StudentCard empty to_user_name crash (RED repro)", () => {
  it("control: valid name does not throw (GREEN — confirms setup)", () => {
    expect(() => render(<StudentCard conn={makeConn({ to_user_name: "Alice" })} />)).not.toThrow()
  })

  it('control: null name does not throw — `?? "?"` catches null (GREEN — proves ?? works for null)', () => {
    expect(() => render(<StudentCard conn={makeConn({ to_user_name: null })} />)).not.toThrow()
  })

  it("BUG #1: empty-string name throws TypeError (RED — `??` misses empty string)", () => {
    // CONTRACT: StudentCard must render gracefully when to_user_name === "".
    // RED: ("" ?? "?")[0] === ""[0] === undefined → undefined.toUpperCase()
    //      throws TypeError → coach dashboard breaks.
    expect(() => render(<StudentCard conn={makeConn({ to_user_name: "" })} />)).not.toThrow()
  })
})
