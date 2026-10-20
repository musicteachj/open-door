import React from 'react';
import { Button } from '../core/Button.jsx';
import { StatusBadge } from './StatusBadge.jsx';
import { Avatar } from '../core/Avatar.jsx';

export function RequestRow({ type = 'pto', dates, amount, status, decidedBy, note, canCancel = false, onCancel, loading = false, cancelState, person, decidedLine, noteLabel, 'data-state': state }) {
  if (loading) {
    return (
      <li className="od-req" aria-hidden="true">
        <span className="od-req__main" style={{ gap: 10 }}><span className="od-skel" style={{ width: 200 }} /><span className="od-skel" style={{ width: 120, height: 10 }} /></span>
        <span className="od-skel" style={{ width: 96, height: 24, borderRadius: 6 }} /><span />
      </li>
    );
  }
  const typeLabel = type === 'sick' ? 'Sick time' : 'PTO';
  const by = decidedLine || (decidedBy && (status === 'approved' || status === 'denied') ? (status === 'denied' ? 'Denied by ' : 'Approved by ') + decidedBy : null);
  return (
    <li className={'od-req' + (person ? ' od-req--person' : '')} data-state={state}>
      {person && <div className="od-req__person"><Avatar initials={person.initials} size={32} />{person.name}</div>}
      <div className="od-req__main"><span className="od-req__dates">{dates}</span><span className="od-req__meta">{typeLabel} · {amount}</span></div>
      <div className="od-req__status"><StatusBadge status={status} />{by && <span className="od-req__by">{by}</span>}</div>
      {!person && <div className="od-req__action">
        {canCancel && <Button variant="secondary" size="sm" aria-label={'Cancel ' + typeLabel + ' on ' + dates} onClick={onCancel} data-state={cancelState}>Cancel</Button>}
      </div>}
      {note && <div className="od-req__note"><span>{noteLabel || decidedBy + '’s note'}</span><p>“{note}”</p></div>}
    </li>
  );
}

export function RequestGroup({ title, empty, children }) {
  return (
    <div style={{ marginTop: 24 }}>
      <h3 className="od-req-group__title">{title}</h3>
      {empty && <p className="od-req-empty">{empty}</p>}
      <ul role="list" className="od-req-list">{children}</ul>
    </div>
  );
}
