ConfirmCard is how the assistant proposes an action. It never acts on its own.

~~~jsx
<ConfirmCard title="Book PTO" icon="calendar-plus" state={state}
  facts={[{ label: 'Type', value: 'PTO' }, { label: 'Dates', value: 'Friday, October 30' }]}
  preview={{ counted: [{ label: 'Friday, October 30', hours: '8 hours' }], amount: '8 hours (1 day)', left: '84 hours (10.5 days) left after this' }}
  info="Marcus Bell, your manager, reviews PTO requests." sources={[{ label: 'Handbook §4.1 · Paid time off', href: '/handbook/4.1' }]}
  confirmAria="Confirm: book PTO on Friday, October 30" dismissAria="Dismiss, don't book PTO on Friday, October 30"
  executedText="Requested. Marcus Bell will review it." executedLink={{ label: 'View in Time off', href: '/time-off' }} badge="waiting" />
~~~

- Every figure comes from the time-off engine. The assistant's line above the card never repeats or claims them, and never says "booked", "approved", or "done".
- Confirm is primary on every card, deny included: it confirms what the person already chose. No red except real errors.
- While the answer is still streaming, Confirm is disabled with "Wait for the answer to finish".
- The secondary button is "Dismiss", never "Cancel", so it never reads as the "Cancel time off" action.
- Executed decision cards link to Approvals ("View in Approvals"); the rest link to Time off.
- After any final state the buttons are gone and the card stays as a record.
- One pending card per conversation. A newer card replaces the older one ("Replaced by a newer card. Nothing was changed.").
- No pronouns. Name the person or the page: "Priya will see it on the Time off page."
- On a sensitive turn the card is a routine record; the escalation panel comes after it, separately.
