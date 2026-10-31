# CoachMark

~~~jsx
<TourRing rect={composerRect} radius={12} />
<CoachMark id="t1" step={1} title="Ask a policy question" body="You're Priya Raman, …" chips={['How many sick days do I get?']}
  sent={sent} resultShown={answered} side="bottom" pointer={40} style={{ left, top }} headingRef={h}
  onSend={send} onNext={next} onBack={back} onSkip={skip} onLeave={leave} />
~~~

- 360 px card, border-strong edge, shadow-md, 12 px pointer toward the target. The target gets `TourRing`. No overlay, no spotlight, no dimming: the page stays usable.
- Top: "Step 3 of 10" (muted, hidden from screen readers because the title repeats it) and the X, labeled "Leave the tour".
- Footer: Back (secondary, hidden on step 1); "Skip this step" (ghost) until the step's result appears, then Next (primary) in its place. Steps without chips show Next from the start.
- `missing`: when the answer finishes without the expected result (no card, no panel), a muted line says what would have appeared, and Next shows.
- Focus moves to the title on every new step (`tabIndex=-1`), which announces "Step 3 of 10: Book a day off". Escape leaves. Tab moves through the chips and buttons, then on to the page.
- Placement: beside the target with a 12 px gap, flipping sides to stay on screen. Under `prefers-reduced-motion` it moves instantly; it never slides or scrolls with animation.
- Phone: docks to the bottom as a sheet (no pointer); the target scrolls into view above it.
- shadcn: Popover (non-modal) anchored to the target; the ring is a positioned sibling.
