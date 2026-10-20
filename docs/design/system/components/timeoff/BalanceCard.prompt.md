BalanceCard shows what someone has, and how it was worked out.

~~~jsx
<BalanceCard id="pto" label="PTO available" hours="92 hours" days="11.5 days"
  source={{ href: '/handbook/4.1', label: 'Handbook §4.1 · Paid time off' }}
  rows={[{ label: 'Earned to date', value: '132 hours' }, { label: 'Taken', value: '32 hours' }, { label: 'Booked', value: '8 hours' }, { label: 'Waiting for approval', value: '0 hours' }]}
  footer={['Next: 10 hours on October 31', 'You can save up to 180 hours.']} />
~~~

- Every figure comes from the time-off engine. The ledger must add up to the big figure.
- No charts, progress bars, or streaks. This is a record.
