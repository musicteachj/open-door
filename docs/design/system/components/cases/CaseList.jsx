import React from 'react';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';

// My cases: status only. Rows are not links and never show the person's words.
// cases: [{ id, category, sent: 'Sent Mon, Oct 26', status: 'case-sent' | 'case-reviewing' | 'case-finished', line }]
export function CaseList({ cases = [] }) {
  return (
    <ul role="list" aria-label="Your cases" className="od-case-list">
      {cases.map((c) => (
        <li key={c.id || c.sent + c.category} className="od-case-row">
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}><span className="od-case-row__cat">{c.category}</span><span className="od-case-row__sent">{c.sent}</span></span>
          <span><StatusBadge status={c.status} /></span>
          <span className="od-case-row__line">{c.line}</span>
        </li>
      ))}
    </ul>
  );
}
