# TracePanel

~~~jsx
<TracePanel id="t-trace" title="10:31 AM · Employee · Oakland, CA" safety={{ ms: '640 ms' }}
  tools={[{ label: 'Searched the handbook', name: 'search_handbook', ms: '420 ms' }]}
  sections={[{ num: 'CA-4.3', title: 'Sick leave (California)', cited: true }, { num: '4.3', title: 'Sick leave', cited: false }]}
  model={{ id: 'claude-opus-5-5', effort: 'low', prompt: '2026-11.2', tools: '2026-11.2' }}
  tokens={{ input: '12,400', cached: '10,200', output: '470', cacheWrites: '0' }} cost="$0.021"
  timings={{ safety: '640 ms', firstToken: '1.4 s', total: '4.1 s' }} onClose={close} headingRef={h} />
~~~

- Docks on the right at --panel-width (420 px) like the passage panel; on phones it's a full-screen sheet.
- Opening focuses the heading. Escape or X closes and returns focus to the row. Opening another row swaps the content.
- A refusal shows only its category ("Category: general harms"), never the explanation. First token reads "No answer text" when nothing streamed.
- A fallback adds "Served by claude-sonnet-5-5 after a fallback" under Model. A failed tool shows "Failed" with the danger icon beside its duration; it's an error, so red is allowed there and only there.
- No tool inputs, no question, no answer.
