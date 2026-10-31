# TourChip

~~~jsx
<TourChip text="How many sick days do I get?" onSend={send} />
<TourChip text="How many sick days do I get?" sent />
~~~

- The "Try asking" row style, sized for the coach mark: 44 px minimum, 14 px text, trailing arrow.
- Clicking sends the text as the current persona, exactly as if typed. Sent: muted text, check and "Sent", aria-disabled, still focusable, named "…, sent".
- One or two per step. Steps 8 and 9 have none.
