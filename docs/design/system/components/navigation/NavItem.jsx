import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function NavItem({ icon, label, href = '#', current = false, count, countLabel = 'waiting', className = '', ...rest }) {
  return (
    <a href={href} className={'od-nav-item ' + className} aria-current={current ? 'page' : undefined} {...rest}>
      {icon && <Icon name={icon} size={18} />}
      <span className="od-truncate" style={{ flex: 1 }}>{label}</span>
      {count ? <span className="od-nav-count"><span aria-hidden="true">{count}</span><span className="od-sr-only">, {count} {countLabel}</span></span> : null}
    </a>
  );
}
