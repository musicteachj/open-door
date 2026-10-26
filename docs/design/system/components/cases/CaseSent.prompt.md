# CaseSent

The sent state that replaces the form, and the "5 cases waiting" limit.

~~~jsx
<div className="od-case-band"><CaseSent /></div>
<div className="od-case-card"><CaseSent showLink={false} /></div>
<div className="od-case-band"><CaseSent variant="limit" /></div>
~~~

- Lock icon, one line, "View in My cases" in the conversation. No apricot, no check, no celebration.
- role="status", tabIndex -1; focus moves to it after sending. A reload renders exactly this.
- If the safety check routes the words to crisis, render screen 07's crisis panel right after it, unchanged.
