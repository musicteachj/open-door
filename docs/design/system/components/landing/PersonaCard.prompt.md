PersonaCard is one person in the landing page's "Choose who to be" picker; selecting it starts a private sandbox as that person.

~~~jsx
<div className="od-persona-grid">
  <PersonaCard name="Priya Raman" role="Visual Merchandiser" location="Oakland store"
    prompt="Ask about California sick leave and book a day off." status={who === 'priya' ? 'starting' : 'idle'}
    disabled={!!who && who !== 'priya'} onSelect={() => start('priya')} />
</div>
~~~

- States: default, hover (border darkens to input-border-hover), focus (2 px ring), starting (primary border, spinner, aria-busy), disabled (others while one starts).
- If starting fails, re-enable every card and show InlineError under the grid: "We couldn't start a sandbox." with Retry.
- Announce starting in a polite live region; the spinner stops under prefers-reduced-motion.
- od-persona-grid lays out four across at 1168 px and wraps to fewer columns at 240 px each.
