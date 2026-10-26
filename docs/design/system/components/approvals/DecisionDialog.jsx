import React from 'react';
import { Button } from '../core/Button.jsx';
import { NoteField } from './NoteField.jsx';

/** Approve or deny one PTO request. kind: 'approve' | 'deny'. phase: null | 'deciding'. */
export function DecisionDialog({ id = 'decide', kind = 'approve', person, facts, note = '', onNoteChange, phase, onConfirm, onBack, scrim = true, backState, noteState }) {
  const deny = kind === 'deny', busy = phase === 'deciding';
  const ref = React.useRef(null);
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); if (!busy && onBack) onBack(); return; }
    if (e.key !== 'Tab' || !ref.current) return;
    const els = Array.from(ref.current.querySelectorAll('button:not([disabled]), textarea:not([disabled])'));
    if (!els.length) return;
    const first = els[0], last = els[els.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  const body = deny ? facts : facts + ' ' + person.first + ' will see it on the Time off page.';
  const dialog = (
    <div ref={ref} role="alertdialog" aria-modal={scrim || undefined} aria-labelledby={id + '-t'} aria-describedby={id + '-b'} className="od-dialog" onKeyDown={onKey}>
      <h2 id={id + '-t'} className="od-dialog__title">{(deny ? 'Deny ' : 'Approve ') + person.name + '’s PTO?'}</h2>
      <p id={id + '-b'} className="od-dialog__body">{body}</p>
      {deny && <NoteField id={id + '-note'} label={'Note to ' + person.first + ' (optional)'} helper={person.first + ' will see this note. Up to 300 characters.'} value={note} disabled={busy} onChange={onNoteChange} data-state={noteState} />}
      <div className="od-dialog__actions">
        <Button variant="secondary" disabled={busy} onClick={onBack} data-state={backState}>Go back</Button>
        <Button variant="primary" loading={busy} onClick={onConfirm}>{busy ? (deny ? 'Denying…' : 'Approving…') : (deny ? 'Deny' : 'Approve')}</Button>
      </div>
    </div>
  );
  return scrim ? <div className="od-scrim">{dialog}</div> : dialog;
}
