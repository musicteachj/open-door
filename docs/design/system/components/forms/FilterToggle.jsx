import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function FilterToggle({ label, icon = 'users', count, pressed = false, onChange, className = '', ...rest }) {
  return (
    <button type="button" className={'od-filter-toggle ' + className} aria-pressed={pressed} onClick={() => onChange && onChange(!pressed)} {...rest}>
      <Icon name={pressed ? 'check' : icon} size={16} strokeWidth={pressed ? 2 : 1.75} className="od-filter-toggle__icon" />
      {label}
      {count != null && <span className="od-filter-toggle__count">{count}</span>}
    </button>
  );
}
