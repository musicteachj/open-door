PreviewBlock shows exactly what a request uses before it's sent.

~~~jsx
<PreviewBlock counted={[{ label: 'Friday, October 30', hours: '8 hours' }, { label: 'Monday, November 2', hours: '8 hours' }]}
  skipped={['Saturday, October 31 and Sunday, November 1 aren’t on your schedule']}
  amount="16 hours (2 days)" left="76 hours (9.5 days) left after this" />
~~~

- Every number comes from the time-off engine, the same one the assistant's confirm cards use.
- More than five counted days collapse into runs ("Monday, November 30 to Friday, December 4 · 40 hours").
