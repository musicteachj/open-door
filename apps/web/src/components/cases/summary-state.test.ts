import { describe, expect, it } from 'vitest'
import type { CaseSummaryOut, CaseDetailOut } from '@/api/generated'
import { summaryRetryKind, summaryStateOf } from './summary-state'

const SENT = '2026-10-26T16:41:00Z'
const detail = (over: Partial<CaseDetailOut> = {}) => ({
  screening: null,
  sentAt: SENT,
  summary: { status: 'none' as const },
  ...over,
})
const at = (secondsAfter: number) => new Date(Date.parse(SENT) + secondsAfter * 1000)
const written: CaseSummaryOut = { status: 'written', text: 'x' }

describe('summaryStateOf', () => {
  it('is written when the fetched summary is written', () => {
    expect(summaryStateOf(detail({ summary: { status: 'written' } }), written, at(5))).toBe(
      'written',
    )
  })

  it('is pending while the detail says written and the text is still being fetched', () => {
    expect(summaryStateOf(detail({ summary: { status: 'written' } }), null, at(5))).toBe('pending')
  })

  it('is failed when the summary failed, whatever the reason', () => {
    for (const reason of ['error', 'screening-conflict', 'unscreened', null]) {
      expect(
        summaryStateOf(
          detail({ summary: { status: 'failed', reason } }),
          { status: 'failed', reason },
          at(5),
        ),
      ).toBe('failed')
    }
  })

  it('is crisis when the case was screened as crisis', () => {
    expect(summaryStateOf(detail({ screening: 'crisis' }), null, at(5))).toBe('crisis')
  })

  it('is crisis when the summary’s reason is crisis, even on a failed summary', () => {
    expect(
      summaryStateOf(
        detail({ summary: { status: 'failed', reason: 'crisis' } }),
        { status: 'failed', reason: 'crisis' },
        at(5),
      ),
    ).toBe('crisis')
    expect(summaryStateOf(detail(), { status: 'none', reason: 'crisis' }, at(5))).toBe('crisis')
  })

  it('is pending when there is no summary yet and the case is new', () => {
    expect(summaryStateOf(detail(), { status: 'none' }, at(30))).toBe('pending')
    expect(summaryStateOf(detail({ summary: null }), null, at(119))).toBe('pending')
  })

  it('is failed, so "Try again" shows, once the case is two and a half minutes old', () => {
    expect(summaryStateOf(detail(), { status: 'none' }, at(150), false)).toBe('failed')
    expect(summaryStateOf(detail(), null, at(600))).toBe('failed')
  })

  it('keeps a margin past the server’s two minutes, for a client clock that runs fast', () => {
    expect(summaryStateOf(detail(), { status: 'none' }, at(120))).toBe('pending')
    expect(summaryStateOf(detail(), { status: 'none' }, at(149))).toBe('pending')
  })

  it('applies the same time rule when the detail says written but the summary is none', () => {
    const d = detail({ summary: { status: 'written' } })
    expect(summaryStateOf(d, { status: 'none' }, at(30))).toBe('pending')
    expect(summaryStateOf(d, { status: 'none' }, at(150))).toBe('failed')
    // Still fetching (null): pending, whatever the age.
    expect(summaryStateOf(d, null, at(600))).toBe('pending')
  })

  it('is failed when the summary fetch itself failed, even if the detail says written', () => {
    expect(summaryStateOf(detail({ summary: { status: 'written' } }), null, at(5), true)).toBe(
      'failed',
    )
  })

  it('still says crisis when the fetch failed on a crisis case', () => {
    expect(summaryStateOf(detail({ screening: 'crisis' }), null, at(5), true)).toBe('crisis')
  })

  it('retries by fetching again when the fetch failed, and by writing again otherwise', () => {
    expect(summaryRetryKind(true)).toBe('refetch')
    expect(summaryRetryKind(false)).toBe('rewrite')
  })
})
