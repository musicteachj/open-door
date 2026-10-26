import React from 'react';
import { Icon } from '../core/Icon.jsx';

// The person's own words, hidden on every view until HR reveals them. Each reveal is recorded (onReveal) and added to the timeline.
// A disclosure button: aria-expanded + aria-controls; focus stays on it.
export function CaseWordsReveal({ id = 'words', firstName, words, open = false, onToggle, buttonState }) {
  return (
    <section aria-labelledby={id + '-h'} className="od-words">
      <h2 id={id + '-h'} className="od-words__title"><Icon name="lock" />{firstName}’s words</h2>
      {!open && <p className="od-words__hidden">{firstName}’s words are hidden. Opening them is recorded in this case’s timeline.</p>}
      <div id={id + '-body'}>{open && <p className="od-words__text">{words}</p>}</div>
      <div><button type="button" className="od-btn od-btn--secondary" aria-expanded={open} aria-controls={id + '-body'} data-state={buttonState} onClick={onToggle}>
        <Icon name={open ? 'eye-off' : 'eye'} size={16} />{(open ? 'Hide ' : 'Show ') + firstName + '’s words'}
      </button></div>
    </section>
  );
}
