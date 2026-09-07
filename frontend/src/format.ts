// Intl may format exact decimal strings at runtime. BigInt formatting also preserves
// all integer digits on browsers where NumberFormat still coerces strings to Number.
export function decimal(value: string, locale: string, precision?: number): string {
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) return value
  const [integer, originalFraction = ''] = value.split('.')
  const fraction = precision === undefined ? originalFraction.replace(/0+$/, '') : originalFraction.replace(/0+$/, '').padEnd(precision, '0')
  const safeLocale = validLocale(locale)
  const formatter = new Intl.NumberFormat(safeLocale, { useGrouping: true, maximumFractionDigits: 0 })
  let formatted = formatter.format(BigInt(integer!))
  if (integer === '-0') formatted = new Intl.NumberFormat(safeLocale).format(-0)
  if (!fraction) return formatted
  const separator = new Intl.NumberFormat(safeLocale).formatToParts(1.1).find(part => part.type === 'decimal')?.value ?? '.'
  const digitFormatter = new Intl.NumberFormat(safeLocale, { useGrouping: false })
  const digits = fraction.replace(/\d/g, digit => digitFormatter.format(Number(digit)))
  return formatted + separator + digits
}
export function money(value: string | undefined, currency: string, locale: string, precision: number): string {
  return `${decimal(value ?? '0', locale, precision)}\u00a0${currency}`
}
export function date(value: string, locale: string): string {
  if (!value) return ''
  const parsed = new Date(value.includes('T') ? value : `${value}T12:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(validLocale(locale), { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(parsed)
}
function validLocale(locale: string): string { try { return Intl.getCanonicalLocales(locale)[0] ?? 'fr-FR' } catch { return 'fr-FR' } }
export function today(): string { const current = new Date(); return `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}-${String(current.getDate()).padStart(2, '0')}` }
export function isZero(value: string): boolean { return /^-?0+(?:\.0+)?$/.test(value) }
