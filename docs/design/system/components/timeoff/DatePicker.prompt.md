DatePicker picks the days for a time-off request.

~~~jsx
<DatePicker id="dates-cal" month={month} start={s} end={e} inProgress={picking}
  hoverKey={hover} focusKey={focus} today="2026-10-20" minKey={type === 'pto' ? today : thirtyDaysAgo}
  holidays={{ '2026-11-26': 'Thanksgiving' }} workdays={[1, 2, 3, 4, 5]}
  onSelect={pick} onMonthChange={setMonth} onHoverChange={setHover} onFocusChange={setFocus} onDone={close} />
~~~

- Holidays and the schedule come from the time-off engine; never hard-code them.
- Don't block off-schedule days; the preview explains that they're skipped.
- On a phone it fills the sheet's width; cells stay at least 44 px.
