import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function DirectoryRow({ name, initials, title, department, location, href = '#', isYou = false, onOpen, className = '', ...rest }) {
  const ini = initials || name.split(' ').map((w) => w[0]).join('').slice(0, 2);
  return (
    <a role="listitem" href={href} className={'od-dir-cols od-dir-row ' + className}
      aria-label={name + ', ' + title + ', ' + department + ', ' + location + (isYou ? ' (you)' : '')}
      onClick={(e) => { if (onOpen) { e.preventDefault(); onOpen(); } }} {...rest}>
      <span className="od-dir-row__name">
        <span className="od-dir-avatar" aria-hidden="true">{ini}</span>
        <span className="od-dir-row__person od-truncate">{name}</span>
        {isYou && <span className="od-you">You</span>}
      </span>
      <span className="od-dir-row__cell od-truncate">{title}</span>
      <span className="od-dir-row__cell od-dir-row__cell--muted od-truncate">{department}</span>
      <span className="od-dir-row__cell od-dir-row__cell--muted od-truncate">{location}</span>
      <Icon name="chevron-right" size={16} className="od-dir-row__chev" />
    </a>
  );
}
