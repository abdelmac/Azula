import { describe, expect, it } from 'vitest'
import { date, decimal, isZero, money } from './format'

describe('Formatage décimal exact', () => {
  it('conserve les centimes et les grandes valeurs au-delà de Number.MAX_SAFE_INTEGER', () => {
    expect(decimal('9007199254740993123456.01', 'en-US', 2)).toBe('9,007,199,254,740,993,123,456.01')
    expect(money('120.00', 'EUR', 'fr-FR', 2)).toBe('120,00\u00a0EUR')
  })
  it('conserve les prix unitaires plus précis que la devise, sans arrondir silencieusement', () => {
    expect(decimal('0.123456', 'en-US', 2)).toBe('0.123456')
    expect(decimal('100.000000', 'en-US', 2)).toBe('100.00')
    expect(decimal('1.000000', 'en-US')).toBe('1')
  })
  it('formate l’arabe, les négatifs et le zéro sans calcul monétaire flottant', () => {
    expect(decimal('120.50', 'ar-EG-u-nu-arab', 2)).toContain('١٢٠٫٥٠')
    expect(decimal('-0.12', 'en-US', 2)).toBe('-0.12')
    expect(isZero('0.0000')).toBe(true)
    expect(isZero('0.0001')).toBe(false)
  })
  it('sépare langue, devise et région et fournit un secours sur les valeurs invalides', () => {
    expect(money('120.00', 'TRY', 'de-DE', 2)).toBe('120,00\u00a0TRY')
    expect(decimal('12.50', 'invalid_locale', 2)).toBe('12,50')
    expect(date('invalid-date', 'fr-FR')).toBe('invalid-date')
    expect(date('2026-09-07', 'en-GB')).toBe('07 Sept 2026')
    expect(decimal('invalid', 'fr-FR')).toBe('invalid')
  })
})
