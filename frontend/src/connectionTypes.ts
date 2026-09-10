export const integrationScopes = ['catalog:read', 'customers:read', 'customers:write', 'invoices:read', 'invoices:write', 'transactions:write', 'banking:read'] as const
export type IntegrationScope = typeof integrationScopes[number]
export interface Integration { id: number; name: string; kind: 'website' | 'payments' | 'bank' | 'other'; provider: string; enabled: boolean; created_at: string }
export interface IntegrationKey { id: number; integration: number; name: string; prefix: string; scopes: IntegrationScope[]; expires_at: string; revoked_at: string | null; created_at: string }
export interface BankAccount { id: number; name: string; bank_name: string; iban: string; bic: string; currency: string; archived: boolean }
export interface BankTransaction { id: number; account: number; account_name: string; external_id: string; date: string; amount: string; description: string; reference: string; invoice: number | null; invoice_number: string; payment: number | null; reconciled_at: string | null }
export interface ExternalTransaction { id: number; integration: number; integration_name: string; external_id: string; date: string; amount: string; currency: string; reference: string; status: 'received' }
export interface CsvPreview { rows: { external_id: string; date: string; amount: string; description: string; reference: string }[]; count: number; duplicates: number; created: number; total: string; confirmed: boolean; preview_digest: string }
export interface ApiSchema { endpoints: { method: string; path: string; scope: string; example?: Record<string, unknown> }[] }
