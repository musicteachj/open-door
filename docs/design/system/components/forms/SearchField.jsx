import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function SearchField({ value, onChange, placeholder = 'Search by name, title, or email', label = 'Search the directory by name, title, or email', className = '', ...rest }) {
  return (
    <div className={'od-search ' + className} role="search" {...rest}>
      <Icon name="search" size={16} className="od-search__icon" />
      <input type="search" className="od-search__input" aria-label={label} value={value} placeholder={placeholder}
        onChange={(e) => onChange && onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Escape' && value) onChange && onChange(''); }} />
      {value ? <button type="button" className="od-search__clear" aria-label="Clear search" onClick={() => onChange && onChange('')}><Icon name="x" size={16} /></button> : null}
    </div>
  );
}
