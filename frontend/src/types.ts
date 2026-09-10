import type { PrintSettings } from './documentTypes'

export const languages = ['fr', 'en', 'ar', 'de', 'tr'] as const
export type Language = typeof languages[number]
export type Role = 'admin' | 'accountant' | 'sales' | 'viewer'
export interface User { id: number; username: string; role: Role; language: Language; company: number | Company; is_active?: boolean }
export interface Company { id: number; name: string; address: string; email: string; currency: string; precision: number; document_language: Language; locale: string; print_settings?: PrintSettings }
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
export interface Customer { id: number; name: string; email: string; address: string; tax_id: string; archived: boolean; default_discount_rate?: string; payment_terms_days?: number; shipping_address?: string }
export interface CatalogReference { id: number; code: string; name: string; archived: boolean }
export type CatalogKind = 'product-categories' | 'warehouses' | 'units'
export interface Product { id: number; reference: string; name: string; unit_price: string; tax_rate: string; archived: boolean; category?: number | null; category_name?: string; unit?: number | null; unit_name?: string; warehouses?: number[]; purchase_price?: string | null; specifications?: string; image_url?: string }
export interface InvoiceLine { id?: number; product: number | null; description: string; quantity: string; unit_price: string; tax_rate: string; discount_rate?: string; product_reference?: string; net?: string; tax?: string; total?: string }
export interface Payment { id: number; amount: string; date: string; reference: string }
export interface Snapshot { company: Pick<Company, 'name' | 'address' | 'email' | 'currency'>; customer: Pick<Customer, 'name' | 'address' | 'email' | 'tax_id'>; number: string; issue_date: string; due_date: string; lines: InvoiceLine[]; currency: string; precision: number; locale: string; document_language: Language; rounding_policy?: string; rounding?: { mode: string; scope: string; tax_base: string }; net: string; tax: string; total: string; customer_reference?: string; notes?: string; payment_terms?: string; shipping_address?: string; document_title?: string; print_settings?: PrintSettings; status?: 'draft' | 'validated' }
export interface Invoice { id: number; customer: number; customer_name: string; issue_date: string; due_date: string; document_language: Language; status: 'draft' | 'validated'; number: string; lines: InvoiceLine[]; net: string; tax: string; total: string; paid: string; balance: string; snapshot: Snapshot | null; payments: Payment[]; customer_reference?: string; notes?: string; payment_terms?: string; shipping_address?: string; document_title?: string }
export interface Period { id: number; name: string; start: string; end: string; closed: boolean }
export interface Journal { id: number; code: string; name: string }
export interface EntryLine { account: number; account_code: string; debit: string; credit: string }
export interface Entry { id: number; date: string; reference: string; journal: number; journal_code: string; invoice: number; lines: EntryLine[]; total_debit: string; total_credit: string }
export interface TrialBalance { accounts: { code: string; name: string; debit: string; credit: string; balance: string }[]; total_debit: string; total_credit: string }
export interface AuditEvent { id: number; created_at: string; actor_name: string; action: string; object_type: string; object_id: string; metadata: Record<string, unknown> }
