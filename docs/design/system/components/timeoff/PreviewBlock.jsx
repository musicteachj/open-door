import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function PreviewBlock({ id = 'preview', counted = [], skipped = [], amount, left, sources = [], empty = false }) {
  if (empty) return <p className="od-preview-empty">Pick dates to see what this uses.</p>;
  return (
    <section className="od-preview" aria-labelledby={id + '-title'}>
      <h3 id={id + '-title'} className="od-preview__title">What this uses</h3>
      <div className="od-preview__body" aria-live="polite">
        <ul role="list" className="od-preview__list">
          {counted.map((c) => (
            <li key={c.label} className={'od-preview__item' + (c.blocked ? ' od-preview__item--blocked' : '')}>
              <Icon name={c.blocked ? 'circle-alert' : 'check'} size={16} strokeWidth={c.blocked ? 1.75 : 2} />
              <span><span className="od-sr-only">{c.blocked ? 'Can’t be counted: ' : 'Counted: '}</span>{c.label}</span>
              <span>{c.blocked ? 'Already booked' : c.hours}</span>
            </li>
          ))}
          {skipped.map((s) => (
            <li key={s} className="od-preview__item od-preview__item--skip"><Icon name="calendar-minus" size={16} /><span><span className="od-sr-only">Skipped: </span>{s}</span></li>
          ))}
        </ul>
        <p className="od-preview__total"><strong>{amount}</strong>{left && <span className="od-preview__left"> · {left}</span>}</p>
        {sources.length > 0 && (
          <div className="od-preview__sources">
            <span>Sources</span>
            {sources.map((s) => <a key={s.label} className="od-source-chip" href={s.href} aria-label={'Source: ' + s.label.replace(' · ', ', ')}><Icon name="book-open" size={13} />{s.label}</a>)}
          </div>
        )}
      </div>
    </section>
  );
}
