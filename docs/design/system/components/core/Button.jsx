import React from 'react';
import { Icon } from './Icon.jsx';

export function Button({ variant = 'primary', size = 'md', icon, iconRight, loading = false, type = 'button', className = '', children, onClick, ...rest }) {
  const cls = ['od-btn', 'od-btn--' + variant, size === 'sm' ? 'od-btn--sm' : '', iconRight ? 'od-btn--icon-right' : '', className].filter(Boolean).join(' ');
  const s = size === 'sm' ? 14 : 16;
  return (
    <button type={type} className={cls} aria-busy={loading || undefined} aria-disabled={loading || undefined}
      onClick={loading ? undefined : onClick} {...rest}>
      {loading ? <Icon name="loader-circle" size={s} strokeWidth={2} className="od-spin" /> : icon && <Icon name={icon} size={s} />}
      {children}
      {iconRight && !loading && <Icon name={iconRight} size={s} strokeWidth={2} />}
    </button>
  );
}
