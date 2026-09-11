export interface BillingAccess { enabled: boolean; has_access: boolean; exempt: boolean; status: string }
export interface BillingPlan {
  code: string
  name: string
  description: string
  amount: string
  currency: string
  precision: number
  interval: 'month' | 'year'
  trial_days: number
}
export interface Subscription {
  plan_code: string
  plan_name: string
  amount: string
  currency: string
  precision: number
  interval: 'month' | 'year'
  current_period_end: string | null
  trial_end: string | null
  cancel_at_period_end: boolean
}
export interface BillingStatus extends BillingAccess {
  configured: boolean
  can_manage: boolean
  subscription: Subscription | null
  plans: BillingPlan[]
  checkout_pending: boolean
}
