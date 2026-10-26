import { describe, expect, it } from 'vitest'
import {
  CARD_APPROVE,
  CARD_BOOK,
  CARD_CANCEL,
  CARD_CANCEL_SICK,
  CARD_DENY,
  CARD_SICK,
  EXPIRES_AT,
  TIME_ZONE,
} from '@/app/gallery/fixtures/timeoff'
import {
  cardTitle,
  confirmCopy,
  confirmLabel,
  confirmName,
  dismissName,
  endedText,
  executedText,
  expiryLabel,
  failureVerb,
} from './confirm-labels'

describe('expiryLabel', () => {
  it('writes the time in the given zone, with a plain space before PM', () => {
    expect(expiryLabel(EXPIRES_AT, TIME_ZONE)).toBe('3:42 PM')
    expect(expiryLabel(EXPIRES_AT, 'America/New_York')).toBe('6:42 PM')
  })
})

describe('cardTitle and confirmLabel', () => {
  it('names each variant', () => {
    expect(cardTitle(CARD_BOOK)).toBe('Book PTO')
    expect(cardTitle(CARD_SICK)).toBe('Record sick time')
    expect(cardTitle(CARD_APPROVE)).toBe('Approve a request')
    expect(cardTitle(CARD_DENY)).toBe('Deny a request')
    expect(cardTitle(CARD_CANCEL)).toBe('Cancel time off')
  })

  it('reads Deny on a denial and Confirm on every other card', () => {
    expect(confirmLabel(CARD_DENY)).toBe('Deny')
    for (const card of [CARD_BOOK, CARD_SICK, CARD_APPROVE, CARD_CANCEL]) {
      expect(confirmLabel(card)).toBe('Confirm')
    }
  })
})

describe('confirmName and dismissName', () => {
  it('name the action and its dates', () => {
    expect(confirmName(CARD_BOOK)).toBe('Confirm: book PTO on Friday, October 30')
    expect(dismissName(CARD_BOOK)).toBe('Dismiss, don’t book PTO on Friday, October 30')
    expect(confirmName(CARD_SICK)).toBe('Confirm: record sick time on Thursday, October 22')
    expect(confirmName(CARD_DENY)).toBe(
      'Confirm: deny Zara Bautista’s PTO, Monday, November 9 to Tuesday, November 10',
    )
    expect(dismissName(CARD_APPROVE)).toBe(
      'Dismiss, don’t approve Priya Raman’s PTO, Friday, October 30',
    )
    expect(confirmName(CARD_CANCEL)).toBe('Confirm: cancel PTO on Wednesday, December 23')
    expect(dismissName(CARD_CANCEL)).toBe('Dismiss, keep PTO on Wednesday, December 23')
    expect(dismissName(CARD_CANCEL_SICK)).toBe('Dismiss, keep sick time on Thursday, October 22')
  })
})

describe('executedText', () => {
  it('says what happened for each variant, naming the person or the page', () => {
    expect(executedText(CARD_BOOK)).toBe('Requested. Marcus Bell will review it.')
    expect(executedText(CARD_SICK)).toBe('Recorded.')
    expect(executedText(CARD_APPROVE)).toBe('Approved. Priya will see it on the Time off page.')
    expect(executedText(CARD_DENY, { withNote: true })).toBe(
      'Denied. Zara will see your note on the Time off page.',
    )
    expect(executedText(CARD_DENY)).toBe('Denied. Zara will see it on the Time off page.')
    expect(executedText(CARD_CANCEL)).toBe('Canceled. 8 hours are back in your balance.')
    expect(executedText(CARD_CANCEL_SICK)).toBe('Canceled. The sick time is no longer recorded.')
  })
})

describe('endedText and failureVerb', () => {
  it('says nothing was changed for every ending but executed', () => {
    expect(endedText('canceled', 'dismissed')).toBe('You dismissed this. Nothing was changed.')
    expect(endedText('canceled', null)).toBe('You dismissed this. Nothing was changed.')
    expect(endedText('canceled', 'replaced')).toBe('Replaced by a newer card. Nothing was changed.')
    expect(endedText('canceled', 'turn-incomplete')).toBe(
      'This card’s answer didn’t finish. Nothing was changed.',
    )
    expect(endedText('expired', null)).toBe(
      'This card expired after 15 minutes. Nothing was changed.',
    )
  })

  it('has a verb for each variant', () => {
    expect(failureVerb(CARD_BOOK)).toBe('book')
    expect(failureVerb(CARD_SICK)).toBe('record')
    expect(failureVerb(CARD_APPROVE)).toBe('approve')
    expect(failureVerb(CARD_DENY)).toBe('deny')
    expect(failureVerb(CARD_CANCEL)).toBe('cancel')
  })
})

describe('confirmCopy', () => {
  it('has no em dash and no pronoun', () => {
    const text = JSON.stringify(confirmCopy)
    expect(text).not.toContain(String.fromCharCode(0x2014))
    expect(text).not.toMatch(/\b(he|she|him|her|his|hers|they|them|their)\b/i)
  })

  describe('what goes back on a cancellation', () => {
    it('says goes for one hour and go for the rest', () => {
      expect(confirmCopy.amountGoBack('1 hour')).toBe('1 hour goes back')
      expect(confirmCopy.amountGoBack('8 hours (1 day)')).toBe('8 hours (1 day) go back')
      expect(executedText({ ...CARD_CANCEL, returnsLabel: '1 hour' })).toBe(
        'Canceled. 1 hour is back in your balance.',
      )
    })

    it('says only Canceled when nothing goes back to the balance', () => {
      const none = { ...CARD_CANCEL, returnsMinutes: 0, returnsLabel: '0 hours' }
      expect(executedText(none)).toBe('Canceled.')
    })
  })

  describe('the fallback reason', () => {
    it('matches the server’s generic failure text', () => {
      expect(confirmCopy.unknownFailure).toBe('This card could not be completed.')
    })
  })

  describe('amountGoBack, as executedText decides it', () => {
    it('says goes for one hour even when days follow', () => {
      expect(confirmCopy.amountGoBack('1 hour (1 day)')).toBe('1 hour (1 day) goes back')
    })
  })
})
