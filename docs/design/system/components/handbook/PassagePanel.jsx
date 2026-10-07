import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { InlineError } from '../assistant/InlineError.jsx';
import { ApplicabilityBadge } from './ApplicabilityBadge.jsx';
import { AppliesMarker } from './AppliesMarker.jsx';
import { LastUpdated } from './LastUpdated.jsx';
import { CitedPassage } from './CitedPassage.jsx';

export function PassagePanel({ state = 'open', eyebrow, title, applies, appliesToYou, updated, before, cited, after, href, onClose, onOpen, onRetry, className = '' }) {
  const titleRef = React.useRef(null);
  React.useEffect(() => { if (state === 'open' && titleRef.current) titleRef.current.focus(); }, [state]);
  React.useEffect(() => { const k = (e) => { if (e.key === 'Escape' && onClose) onClose(); }; document.addEventListener('keydown', k); return () => document.removeEventListener('keydown', k); }, [onClose]);
  const bar = (w, h = 12, extra) => <span aria-hidden="true" className="od-skel" style={Object.assign({ width: w, height: h }, extra)} />;
  return (
    <aside aria-label="Handbook passage" aria-busy={state === 'loading'} className={'od-panel ' + className}>
      <header className="od-panel__head">
        <div className="od-panel__top">
          <span className="od-panel__eyebrow"><Icon name="book-open" size={14} />{eyebrow}</span>
          <button type="button" className="od-icon-btn" aria-label="Close passage" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        {state === 'open' && <>
          <h2 className="od-panel__title" tabIndex={-1} ref={titleRef}>{title}</h2>
          <div className="od-section-meta" style={{ marginTop: 4 }}><ApplicabilityBadge label={applies} />{appliesToYou != null && <AppliesMarker applies={appliesToYou} />}<LastUpdated date={updated} /></div>
        </>}
        {state === 'loading' && <>{bar(160, 20, { margin: '4px 0' })}{bar(260, 12, { marginTop: 8 })}</>}
      </header>
      <div className="od-panel__body" tabIndex={0} aria-label="Passage text">
        {state === 'open' && <>
          {before && <p className="od-panel__context">{before}</p>}
          <CitedPassage compact id="panel-cited">{cited}</CitedPassage>
          {after && <p className="od-panel__context" style={{ marginBottom: 0 }}>{after}</p>}
        </>}
        {state === 'loading' && <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>{bar('100%')}{bar('92%')}{bar('64%')}{bar('100%', 96, { marginTop: 12, borderRadius: 10 })}{bar('88%', 12, { marginTop: 12 })}{bar('72%')}<span className="od-sr-only">Loading passage</span></div>}
        {state === 'error' && <InlineError message="Couldn't load this passage." onRetry={onRetry} />}
      </div>
      <footer className="od-panel__foot">
        <a href={href} className="od-btn od-btn--secondary od-btn--icon-right" onClick={(e) => { if (onOpen) { e.preventDefault(); onOpen(); } }}>Open in handbook<Icon name="arrow-right" size={16} strokeWidth={2} /></a>
      </footer>
    </aside>
  );
}
