import React from 'react';
import { Icon } from '../core/Icon.jsx';

// A prompt the tour can send as the current persona, in the "Try asking" row style.
// After sending it shows a check and "Sent" and is disabled (aria-disabled, still focusable).
export function TourChip({ text, sent = false, onSend, state }) {
  return (
    <button type="button" className="od-tour-chip" data-state={state} aria-disabled={sent} aria-label={sent ? text + ', sent' : 'Send: ' + text}
      onClick={() => { if (!sent && onSend) onSend(text); }}>
      <span>{text}</span>
      {sent ? <span className="od-tour-chip__sent"><Icon name="check" size={14} strokeWidth={2} />Sent</span> : <Icon name="arrow-right" size={16} />}
    </button>
  );
}
