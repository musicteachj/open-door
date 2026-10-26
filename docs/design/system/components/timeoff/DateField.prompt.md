DateField shows the dates a request covers and opens the picker.

~~~jsx
<DateField id="dates" value={text} open={open} controls="dates-cal" onToggle={() => setOpen(!open)} />
{open && <DatePicker id="dates-cal" ... />}
~~~

- Show the short form so a range fits on one line ("Mon, Nov 2 to Thu, Nov 5") and pass the full form as fullValue. Keep full weekday names everywhere else, including the preview.
- Escape or Done in the picker returns focus here.
