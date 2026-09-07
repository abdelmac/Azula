import { describe, expect, it } from 'vitest'
import { listQuery } from './useList'

describe('Contrat des listes serveur', () => {
  it('omet les filtres Tous pour ne pas envoyer de valeurs invalides à l’API', () => {
    const query = listQuery(1, '', { status: '', archived: '', period: '', journal: '', ordering: '-issue_date' })
    for (const key of ['status', 'archived', 'period', 'journal']) expect(query.has(key)).toBe(false)
    expect(query.get('page_size')).toBe('50')
    expect(query.get('ordering')).toBe('-issue_date')
  })
  it('encode les recherches Unicode et conserve le filtrage et la pagination serveur', () => {
    const query = listQuery(2, 'İstanbul & عميل REF-A12', { status: 'draft', period: '4' })
    const decoded = new URLSearchParams(query.toString())
    expect(decoded.get('search')).toBe('İstanbul & عميل REF-A12')
    expect(decoded.get('page')).toBe('2')
    expect(decoded.get('status')).toBe('draft')
    expect(decoded.get('period')).toBe('4')
  })
})
