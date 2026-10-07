import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { ApplicabilityBadge } from './ApplicabilityBadge.jsx';
import { AppliesMarker } from './AppliesMarker.jsx';

export function SectionRow({ num, title, applies = 'Everyone', appliesToYou = false, updated, href = '#', current = false, onOpen, className = '', ...rest }) {
  return (
    <li>
      <a href={href} className={'od-sec-cols od-sec-row ' + className} aria-current={current ? 'page' : undefined}
        aria-label={num + ' ' + title + '. Applies to ' + applies + (appliesToYou ? '. Applies to you' : '') + '. Last updated ' + updated}
        onClick={(e) => { if (onOpen) { e.preventDefault(); onOpen(); } }} {...rest}>
        <span className="od-sec-row__num">{num}</span>
        <span className="od-sec-row__title">{title}</span>
        <ApplicabilityBadge label={applies} variant="text" />
        <span>{appliesToYou && applies !== 'Everyone' && <AppliesMarker applies />}</span>
        <span className="od-sec-row__date">{updated}</span>
        <Icon name="chevron-right" size={16} className="od-sec-row__chev" />
      </a>
    </li>
  );
}

/** Chapter or addendum heading plus its rows. Rows are plain links in the Tab order. */
export function SectionGroup({ num, title, note, children, id }) {
  return (
    <section aria-labelledby={id}>
      <div className="od-sec-group">
        <span className="od-sec-group__num">{num}</span>
        <div><h2 id={id} className="od-sec-group__title" style={{ display: 'inline' }}>{title}</h2>{note && <span className="od-sec-group__note">{note}</span>}</div>
      </div>
      <ul role="list" className="od-sec-list">{children}</ul>
    </section>
  );
}
