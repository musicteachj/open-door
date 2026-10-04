import React from 'react';
import { Icon } from './Icon.jsx';

export function Button({ variant = 'primary', size = 'md', icon, iconRight, type = 'button', className = '', children, ...rest }) {
  const cls = ['od-btn', 'od-btn--' + variant, size === 'sm' ? 'od-btn--sm' : '', iconRight ? 'od-btn--icon-right' : '', className].filter(Boolean).join(' ');
  const s = size === 'sm' ? 14 : 16;
  return (
    <button type={type} className={cls} {...rest}>
      {icon && <Icon name={icon} size={s} />}
      {children}
      {iconRight && <Icon name={iconRight} size={s} strokeWidth={2} />}
    </button>
  );
}
