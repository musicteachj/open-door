import React from 'react';
import { Icon } from '../core/Icon.jsx';

// The tour's items in the persona menu, between the personas and Sign out (PersonaMenu's extra slot).
// idle: "Take the tour". inProgress: "Resume the tour" with the step under it, and "Start the tour over".
export function TourMenuItems({ step, total = 10, onTake, onResume, onRestart, state }) {
  if (!step) return <button type="button" role="menuitem" className="od-menu__item" data-state={state} onClick={onTake}><Icon name="circle-play" size={16} style={{ color: 'var(--ink-muted)' }} />Take the tour</button>;
  return (
    <>
      <button type="button" role="menuitem" className="od-menu__item od-tour-resume" data-state={state} aria-label={'Resume the tour, step ' + step + ' of ' + total} onClick={onResume}>
        <Icon name="circle-play" size={16} style={{ color: 'var(--ink-muted)' }} /><span><span>Resume the tour</span><span>Step {step} of {total}</span></span>
      </button>
      <button type="button" role="menuitem" className="od-menu__item" onClick={onRestart}><Icon name="rotate-ccw" size={16} style={{ color: 'var(--ink-muted)' }} />Start the tour over</button>
    </>
  );
}

// "Start the tour?" Cancel is focused first; Escape cancels.
export function TourStartDialog({ id = 'tour-start', onStart, onCancel, cancelState }) {
  const ref = React.useRef(null);
  React.useEffect(() => { if (ref.current && !cancelState) ref.current.focus(); }, []);
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby={id + '-t'} aria-describedby={id + '-b'} className="od-tour-dialog" onKeyDown={(e) => { if (e.key === 'Escape' && onCancel) onCancel(); }}>
      <h2 id={id + '-t'}>Start the tour?</h2>
      <p id={id + '-b'}>The tour starts a new sandbox as Priya Raman. Your current sandbox stays until it expires.</p>
      <div className="od-tour-dialog__actions">
        <button type="button" ref={ref} className="od-btn od-btn--secondary" data-state={cancelState} onClick={onCancel}>Cancel</button>
        <button type="button" className="od-btn od-btn--primary" onClick={onStart}>Start the tour</button>
      </div>
    </div>
  );
}
