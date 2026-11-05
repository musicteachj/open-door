# TurnTable

~~~jsx
<TurnTable heading="Monday, October 26 · 9 turns" rows={turns} selectedId={open} onOpen={setOpen} panelOpen={!!open}
  flagged={{ facts: 'Oct 26 · 14,800 input tokens · 550 output · $0.024 · safety check 760 ms · first token 1.9 s · total 5.2 s' }} />
~~~

- ARIA table (role table/row/columnheader/cell) with real headers. Each row's button is named "10:31 AM, Employee, Oakland, CA, Answered" and has aria-expanded and aria-controls pointing at the trace.
- Order is fixed: newest first. No column sorting, no ranking, no scores.
- Never a name, avatar, initials, question, answer, or tool input. "Asked by" is the role and the location's city and state.
- The flagged row always comes after every timed row of the day, so its position doesn't reveal its time. It's plain text, not focusable, and has no trace.
- "Possible prompt injection" is `InjectionTag`: neutral, sunken, muted ink. Beside a docked panel it stacks on two lines.
- shadcn: Table primitives with div rows; the row button is the focus target, the row shows the ring.
