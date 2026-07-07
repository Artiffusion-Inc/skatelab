import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { API_BASE } from "@/lib/api-client"

const SESSION_COOKIE = "sk_session"

export async function getStaffStatus(): Promise<{ isStaff: boolean }> {
  const store = await cookies()
  const token = store.get(SESSION_COOKIE)?.value
  if (!token) return { isStaff: false }
  try {
    const res = await fetch(`${API_BASE}/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    })
    if (!res.ok) return { isStaff: false }
    const data = (await res.json()) as { is_staff?: boolean }
    return { isStaff: !!data.is_staff }
  } catch {
    return { isStaff: false }
  }
}

export async function requireStaff(nextUrl: string): Promise<void> {
  const { isStaff } = await getStaffStatus()
  if (!isStaff) {
    redirect(`/login?next=${encodeURIComponent(nextUrl)}`)
  }
}
