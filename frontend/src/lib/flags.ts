export const FLAGS = {
  RENEWAL_OFFER_VARIANT: "renewal_offer_variant",
  NEW_ONBOARDING_FLOW: "new_onboarding_flow",
  NEW_DASHBOARD: "new_dashboard",
  THREEJS_COMPARISON: "threejs_comparison",
} as const

export type FlagKey = (typeof FLAGS)[keyof typeof FLAGS]
