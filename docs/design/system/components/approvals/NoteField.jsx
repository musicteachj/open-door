import React from 'react';

export function NoteField({ id = 'note', label, helper, value = '', max = 300, disabled = false, onChange, 'data-state': state }) {
  const n = value.length;
  return (
    <div className="od-field od-note">
      <label htmlFor={id} className="od-field-label">{label}</label>
      <textarea id={id} className="od-note__input" rows={4} maxLength={max} value={value} disabled={disabled} data-state={state}
        aria-describedby={id + '-help ' + id + '-count'} onChange={(e) => onChange && onChange(e.target.value.slice(0, max))} />
      <div className="od-note__foot"><span id={id + '-help'}>{helper}</span><span id={id + '-count'} className="od-note__count">{n} of {max}</span></div>
      <span aria-live="polite" className="od-sr-only">{n >= max - 20 ? (max - n) + ' characters left' : ''}</span>
    </div>
  );
}
