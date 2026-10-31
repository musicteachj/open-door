import React from 'react';
import { Icon } from '../core/Icon.jsx';

// The AI's summary of a case, always labeled as the AI's. Neutral, no recommendation.
// state: 'ready' | 'pending' | 'failed' | 'crisis'
export function CaseSummaryBlock({ id = 'sum', state = 'ready', text, writtenAt, model = 'Claude Opus 5.5', onRetry }) {
  return (
    <section aria-labelledby={id + '-h'} aria-busy={state === 'pending' || undefined} className="od-sum">
      <div className="od-sum__head">
        <div className="od-sum__title"><span className="od-ai-tag" aria-hidden="true">AI</span><h2 id={id + '-h'}>AI summary</h2></div>
        {state === 'ready' && <p className="od-sum__meta">Written by Open Door’s AI to be neutral, with no recommendation · {writtenAt} · <span style={{ whiteSpace: 'nowrap' }}>{model}</span></p>}
      </div>
      <div className="od-sum__body">
        {state === 'ready' && <p className="od-sum__text">{text}</p>}
        {state === 'pending' && <div role="status"><p className="od-sum__muted">Writing the summary…</p><div className="od-sum__sk" aria-hidden="true"><span style={{ width: '92%' }} /><span style={{ width: '78%' }} /><span style={{ width: '54%' }} /></div></div>}
        {state === 'failed' && <div className="od-sum__row"><p>No AI summary. Read the person’s words below.</p><button type="button" className="od-btn od-btn--secondary od-btn--sm" onClick={onRetry}><Icon name="rotate-ccw" size={14} />Try again</button></div>}
        {state === 'crisis' && <p>No AI summary for this case. The safety check routed it to crisis text.</p>}
      </div>
    </section>
  );
}
