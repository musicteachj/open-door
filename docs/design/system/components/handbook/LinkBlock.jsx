import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { AppliesMarker } from './AppliesMarker.jsx';

export function LinkBlock({ title, note, links = [], className = '' }) {
  return (
    <div className={'od-linkblock ' + className}>
      <div className="od-linkblock__head"><h2 className="od-linkblock__title">{title}</h2>{note && <span className="od-linkblock__note">{note}</span>}</div>
      <ul role="list" className="od-linkblock__list">
        {links.map((l) => (
          <li key={l.href}>
            <a href={l.href} className="od-linkblock__link" data-state={l['data-state']} onClick={(e) => { if (l.onOpen) { e.preventDefault(); l.onOpen(); } }}>
              <span className="od-linkblock__label">{l.label}{l.meta && <span className="od-linkblock__meta"> · {l.meta}</span>}</span>
              {l.appliesToYou && <AppliesMarker applies />}
              <Icon name="chevron-right" size={16} className="od-sec-row__chev" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
