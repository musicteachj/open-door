import React from 'react';
import { Avatar } from '../core/Avatar.jsx';
import { Button } from '../core/Button.jsx';
import { Icon } from '../core/Icon.jsx';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';
import { FormMessage } from '../timeoff/FormMessage.jsx';

export function ApprovalCard({ person, dates, shortDates, amount, availableAfter, sent, coverage = [], conflict, onApprove, onDeny, loading = false, approveState, denyState }) {
  if (loading) {
    return (
      <li className="od-approval" aria-hidden="true">
        <div className="od-approval__head"><span className="od-approval__who"><span className="od-skel" style={{ width: 40, height: 40, borderRadius: 9999 }} /><span style={{ display: 'flex', flexDirection: 'column', gap: 8 }}><span className="od-skel" style={{ width: 120 }} /><span className="od-skel" style={{ width: 170, height: 10 }} /></span></span></div>
        <div className="od-approval__body"><span style={{ display: 'flex', flexDirection: 'column', gap: 10 }}><span className="od-skel" style={{ width: 360, height: 14 }} /><span className="od-skel" style={{ width: 180, height: 10 }} /><span className="od-skel" style={{ width: 260, height: 10 }} /></span><span style={{ display: 'flex', gap: 12 }}><span className="od-skel" style={{ width: 92, height: 40, borderRadius: 10 }} /><span className="od-skel" style={{ width: 72, height: 40, borderRadius: 10 }} /></span></div>
      </li>
    );
  }
  const muted = !!conflict;
  return (
    <li className="od-approval" data-conflict={muted ? '' : undefined}>
      <div className="od-approval__head">
        <span className="od-approval__who">
          <Avatar initials={person.initials} muted={muted} />
          <span className="od-approval__id"><h3 className="od-approval__name">{person.name}</h3><span className="od-approval__title">{person.title}</span></span>
        </span>
        {muted ? <StatusBadge status="canceled" /> : <span className="od-approval__sent">{sent}</span>}
      </div>
      <div className="od-approval__body">
        <div className="od-approval__facts">
          <p className="od-approval__dates">{dates}</p>
          <p className="od-approval__meta">PTO · {amount}</p>
          <p className="od-approval__after">{availableAfter}</p>
          <div className="od-approval__cov">
            <Icon name="users" size={16} />
            <div><span className="od-approval__cov-label">Team coverage</span>{coverage.map((c) => <span key={c} className="od-approval__cov-line">{c}</span>)}</div>
          </div>
        </div>
        {!muted && (
          <div className="od-approval__actions">
            <Button variant="secondary" data-state={approveState} loading={approveState === 'loading'} disabled={approveState === 'disabled'} aria-label={'Approve ' + person.name + '’s PTO, ' + shortDates} onClick={onApprove}>{approveState === 'loading' ? 'Approving…' : 'Approve'}</Button>
            <Button variant="secondary" data-state={denyState} disabled={denyState === 'disabled'} aria-label={'Deny ' + person.name + '’s PTO, ' + shortDates} onClick={onDeny}>Deny</Button>
          </div>
        )}
      </div>
      {muted && <div role="alert"><FormMessage tone="refusal">{conflict}</FormMessage></div>}
    </li>
  );
}
