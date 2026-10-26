import React from 'react';
import { Avatar } from '../core/Avatar.jsx';
import { Icon } from '../core/Icon.jsx';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';

// HR's case queue. Facts only: person, category, sent, reply, status. Never any part of a case's words or summary.
// Sort order is fixed by the server: new cases by reply date, then the rest oldest first. No other sort exists.
// rows: [{ href, initials, name, title, location, category, crisisFact, sent, reply, status: 'case-new' | 'case-in-review' | 'case-closed' }]
export function CaseQueueTable({ rows = [], emptyText = 'No new cases. A case appears here as soon as someone sends one.' }) {
  return (
    <div className="od-cq">
      <div className="od-cq__head" aria-hidden="true"><span>Person</span><span>Category</span><span>Sent</span><span>Reply</span><span>Status</span><span /></div>
      {rows.length === 0 && <p role="status" className="od-cq__empty">{emptyText}</p>}
      <div role="list" aria-label="Cases">
        {rows.map((r) => (
          <a key={r.href} role="listitem" href={r.href} className="od-cq__row" data-state={r.state}
            aria-label={[r.name + ', ' + r.title + ', ' + r.location, r.category + (r.crisisFact ? '. The safety check routed this message to crisis text' : ''), 'Sent ' + r.sent, r.reply].join('. ')}>
            <span className="od-cq__person"><Avatar initials={r.initials} size={32} /><span><span className="od-cq__name">{r.name}</span><span className="od-cq__sub">{r.title} · {r.location}</span></span></span>
            <span className="od-cq__cat"><span>{r.category}</span>{r.crisisFact && <span className="od-cq__fact"><Icon name="shield" size={13} />The safety check routed this message to crisis text.</span>}</span>
            <span className="od-cq__sent">{r.sent}</span>
            <span className="od-cq__reply">{r.reply}</span>
            <span><StatusBadge status={r.status} /></span>
            <Icon name="chevron-right" size={16} className="od-cq__chev" />
          </a>
        ))}
      </div>
    </div>
  );
}
