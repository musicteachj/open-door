import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { ApplicabilityBadge } from './ApplicabilityBadge.jsx';
import { AppliesMarker } from './AppliesMarker.jsx';
import { LastUpdated } from './LastUpdated.jsx';

export function SearchResultRow({ num, title, group, excerpt, match, applies, appliesToYou, updated, href = '#', onOpen, className = '', ...rest }) {
  let body = excerpt;
  if (excerpt && match) {
    const i = excerpt.toLowerCase().indexOf(match.toLowerCase());
    if (i >= 0) body = <>{excerpt.slice(0, i)}<mark>{excerpt.slice(i, i + match.length)}</mark>{excerpt.slice(i + match.length)}</>;
  }
  return (
    <li>
      <a href={href} className={'od-result ' + className} data-row onClick={(e) => { if (onOpen) { e.preventDefault(); onOpen(); } }} {...rest}>
        <span className="od-result__num">{num}</span>
        <span className="od-result__body">
          <span className="od-result__title">{title}{group && <span className="od-result__group"> · {group}</span>}</span>
          {excerpt && <span className="od-result__excerpt od-truncate">{body}</span>}
          <span className="od-section-meta"><ApplicabilityBadge label={applies} /><AppliesMarker applies={appliesToYou} /><LastUpdated date={updated} /></span>
        </span>
        <Icon name="chevron-right" size={16} className="od-result__chev" />
      </a>
    </li>
  );
}
