import React from 'react';

// Every event on a case, oldest first: sent, summary written, each read of the summary and of the words, each status change.
// New rows are announced politely.
export function CaseTimeline({ id = 'tl', events = [], announce = '' }) {
  return (
    <section aria-labelledby={id + '-h'} className="od-tl">
      <h2 id={id + '-h'}>Timeline</h2>
      <ol>{events.map((e, i) => <li key={i} data-latest={i === events.length - 1 || undefined}><span className="od-tl__text">{e.text}</span><span className="od-tl__time">{e.time}</span></li>)}</ol>
      <span aria-live="polite" className="od-sr-only">{announce}</span>
    </section>
  );
}
