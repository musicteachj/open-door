import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';

// The quiet neutral tag for a possible prompt injection. Never an alert.
export function InjectionTag({ stacked = false }) {
  return <span className="od-inj-tag" data-stack={stacked ? '' : undefined}><span>Possible prompt</span><span>injection</span></span>;
}

// The safety check's category, with the injection tag beneath it when set.
export function SafetyLabel({ category = 'Ordinary', ms, injection = false, stacked = false }) {
  return (
    <span className="od-turns__stack">
      <span className="od-safety"><Icon name="shield-check" size={16} />{category}{ms && <span style={{ color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>· {ms}</span>}</span>
      {injection && <InjectionTag stacked={stacked} />}
    </span>
  );
}

// The sandbox's turns, newest first, in a fixed order. No sorting, ranking, or scoring.
// Never shows a name, initials, question text, answer text, or tool inputs.
// rows: [{ id, time, asker, location, outcome, offeredCard, injection, tools, cited, cost, firstToken, state }]
// flagged: { facts } is rendered after the timed rows, as plain text, never focusable, with no trace.
export function TurnTable({ id = 'turns', heading, rows = [], flagged, selectedId, onOpen, panelOpen = false, loading = false }) {
  const dash = <><span aria-hidden="true" className="od-turns__none">–</span><span className="od-sr">None</span></>;
  return (
    <div className="od-turns" data-panel={panelOpen ? '' : undefined}>
      {heading && <h3 id={id + '-day'} className="od-turns__day">{heading}</h3>}
      <div role="table" aria-labelledby={heading ? id + '-day' : undefined} aria-label={heading ? undefined : 'Turns'} aria-busy={loading || undefined}>
        <div role="rowgroup">
          <div role="row" className="od-turns__head">
            <span role="columnheader">Time</span><span role="columnheader">Asked by</span><span role="columnheader">Outcome</span><span role="columnheader">Safety check</span>
            <span role="columnheader" style={{ textAlign: 'right' }}>Tools</span><span role="columnheader">Cited</span><span role="columnheader" style={{ textAlign: 'right' }}>Cost</span><span role="columnheader" style={{ textAlign: 'right' }}>First token</span>
          </div>
        </div>
        <div role="rowgroup">
          {loading && [0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} role="row" aria-hidden="true" className="od-turns__sk">
              {['70%', '75%', '60%', '55%', '16px', '40%', '44px', '32px'].map((w, j) => <span key={j} className="od-sk" style={{ width: w, justifySelf: j === 4 || j > 5 ? 'end' : undefined }} />)}
            </div>
          ))}
          {rows.map((r) => {
            const sel = r.id === selectedId;
            return (
              <div key={r.id} role="row" className="od-turns__row" aria-selected={sel} data-state={r.state} onClick={() => onOpen && onOpen(r.id)}>
                <span role="cell"><button type="button" className="od-turns__btn" data-turn={r.id} aria-label={[r.time, r.asker, r.location, r.outcomeLabel || 'Answered'].join(', ')} aria-expanded={sel} aria-controls={id + '-trace'}>{r.time}</button></span>
                <span role="cell" className="od-turns__stack" style={{ gap: 0 }}><span>{r.asker}</span><span className="od-turns__muted">{r.location}</span></span>
                <span role="cell" className="od-turns__stack"><StatusBadge status={'outcome-' + (r.outcome || 'answered')} />{r.offeredCard && <span className="od-turns__muted">Offered a card</span>}</span>
                <span role="cell"><SafetyLabel injection={r.injection} stacked={panelOpen} /></span>
                <span role="cell" className="od-turns__num" data-label="Tools">{r.tools}</span>
                <span role="cell" className="od-turns__plain" data-label="Cited">{r.cited || dash}</span>
                <span role="cell" className="od-turns__num">{r.cost}</span>
                <span role="cell" className="od-turns__num" data-label="First token" style={{ whiteSpace: 'nowrap' }}>{r.firstToken}</span>
              </div>
            );
          })}
          {flagged && (
            <div role="row"><div role="cell" className="od-turns__flagged">
              <p><Icon name="lock" size={16} />Flagged by the safety check. Details are hidden to protect the person.</p>
              <p>{flagged.facts}</p>
            </div></div>
          )}
        </div>
      </div>
    </div>
  );
}
