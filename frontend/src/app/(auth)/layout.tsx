import { redirect } from "next/navigation"

export default function AuthLayout() {
  // Public account access is paused while the site is a mobile-app landing page.
  redirect("/")
}
