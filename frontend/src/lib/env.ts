export const devMockAuth = process.env.NEXT_PUBLIC_DEV_MOCK_AUTH === "true"
export const isDevelopment = process.env.NODE_ENV === "development"
export const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? ""
export const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://ph.skatelab.ru"
