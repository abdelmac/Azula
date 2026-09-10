import type { Customer, Page, Payment, Product } from './types'

export interface CustomerDetails extends Customer {
  reference: string; legal_name: string; latin_name: string; contact_name: string
  phone: string; phone_alt: string; mobile: string; fax: string; website: string
  postal_code: string; city: string; region: string; country: string; shipping_address: string
  group_name: string; payment_terms_days: number; default_discount_rate: string; credit_limit: string | null
  bank_name: string; iban: string; bic: string; notes: string; custom_fields: Record<string, string>
}
export interface ProductDetails extends Product {
  latin_name: string; barcode: string; manufacturer: string; supplier_name: string
  color: string; dimensions: string; origin: string; weight: string | null
  notes: string; custom_fields: Record<string, string>
}
export interface CustomerPrice {
  id: number; customer: number; customer_name: string; product: number; product_name: string
  product_reference: string; unit_price: string; archived: boolean
}
export interface StatementRow {
  id: number; number: string; issue_date: string; due_date: string; total: string; paid: string
  balance: string; payments: Payment[]
}
export interface CustomerStatement extends Page<StatementRow> {
  customer: CustomerDetails; currency: string
  summary: { invoice_count: number; total: string; paid: string; balance: string; overdue: string }
}
