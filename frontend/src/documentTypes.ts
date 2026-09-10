export interface PrintSettings {
  layout?: 'standard' | 'compact'
  accent?: string
  footer?: string
  show_product_codes?: boolean
  show_tax?: boolean
  payment_details?: string
  logo_url?: string
}

export const defaultPrintSettings: Required<PrintSettings> = {
  layout: 'standard', accent: '#075ad6', footer: '', show_product_codes: true,
  show_tax: true, payment_details: '', logo_url: '',
}
