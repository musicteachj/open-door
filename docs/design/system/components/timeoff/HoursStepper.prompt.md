HoursStepper takes a small whole number of hours.

~~~jsx
<HoursStepper id="sick-hours" value={hours} onChange={setHours}
  error={valid ? null : 'Enter a whole number from 1 to 8.'} />
~~~

- Range comes from the schedule (1 to 8 for an 8-hour day).
- The error blocks submit; the preview shows 0 hours until it's fixed.
