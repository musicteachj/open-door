import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function NavItem({ icon, label, href = '#', current = false, className = '', ...rest }) {
  return (
    <a href={href} className={'od-nav-item ' + className} aria-current={current ? 'page' : undefined} {...rest}>
      {icon && <Icon name={icon} size={18} />}
      <span className="od-truncate">{label}</span>
    </a>
  );
}
