import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { TourChip } from './TourChip.jsx';

// The 2 px primary ring around a tour target, drawn 4 px outside it. Never a dark overlay or a cutout.
export function TourRing({ rect, radius = 8 }) {
  if (!rect) return null;
  return <div aria-hidden="true" className="od-tour-ring" style={{ left: rect.x - 4, top: rect.y - 4, width: rect.w + 8, height: rect.h + 8, borderRadius: radius + 4 }} />;
}

// One step of the guided tour: a non-modal dialog beside its target, labeled by its title.
// side: where the card sits relative to the target ('bottom' | 'top' | 'right'); pointer: px along that edge.
// The footer shows Skip this step until the step's result appears (or there are no chips), then Next.
export function CoachMark({
  id = 'coach', step, total = 10, title, body, missing, chips = [], sent = [], resultShown = false,
  side = 'bottom', pointer = 40, onBack, onNext, onSkip, onLeave, onSend, headingRef, style, className = ''
}) {
  const done = resultShown || chips.length === 0;
  const stepText = 'Step ' + step + ' of ' + total;
  return (
    <div role="dialog" aria-modal="false" aria-labelledby={id + '-t'} className={'od-coach ' + className} data-side={side} style={style}
      onKeyDown={(e) => { if (e.key === 'Escape' && onLeave) { e.preventDefault(); onLeave(); } }}>
      <span aria-hidden="true" className="od-coach__ptr" style={side === 'right' ? { top: pointer } : { left: pointer }} />
      <div className="od-coach__bar">
        <span aria-hidden="true" className="od-coach__step">{stepText}</span>
        <button type="button" className="od-icon-btn" aria-label="Leave the tour" onClick={onLeave}><Icon name="x" size={16} /></button>
      </div>
      <h2 id={id + '-t'} ref={headingRef} tabIndex={-1} className="od-coach__title"><span className="od-sr">{stepText}: </span>{title}</h2>
      <p className="od-coach__body">{body}</p>
      {missing && <p role="status" className="od-coach__missing">{missing}</p>}
      {chips.length > 0 && <div className="od-coach__chips">{chips.map((c, i) => <TourChip key={c} text={c} sent={sent.includes(i)} onSend={() => onSend && onSend(i)} />)}</div>}
      <div className="od-coach__foot">
        {step > 1 && <button type="button" className="od-btn od-btn--secondary od-btn--sm" onClick={onBack}>Back</button>}
        <span style={{ flex: 1 }} />
        {done ? <button type="button" className="od-btn od-btn--primary od-btn--sm" onClick={onNext}>Next</button>
          : <button type="button" className="od-btn od-btn--ghost od-btn--sm" onClick={onSkip}>Skip this step</button>}
      </div>
    </div>
  );
}
