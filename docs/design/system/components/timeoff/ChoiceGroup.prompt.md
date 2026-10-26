ChoiceGroup is for a short either-or with a little more text, such as Full day or Half day (4 hours).

~~~jsx
<ChoiceGroup id="amount" label="How much" value={amt} onChange={setAmt}
  options={[{ value: 'full', label: 'Full day' }, { value: 'half', label: 'Half day (4 hours)' }]} />
~~~

- Show it only when one day is picked; ranges always count full days.
- For sick time the second option is "Some hours", which reveals HoursStepper.
