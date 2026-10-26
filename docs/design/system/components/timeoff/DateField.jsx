import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function DateField({ id = 'dates', label = 'Dates', value, fullValue, placeholder = 'Pick a day or a range', open = false, controls, error, disabled = false, onToggle, 'data-state': state }) {
  return (
    <div className="od-field">
      <span id={id + '-label'} className="od-field-label">{label}</span>
      <button type="button" id={id} className="od-datefield" aria-expanded={open} aria-controls={controls}
        aria-labelledby={id + '-label ' + id + '-value'} aria-invalid={error ? true : undefined}
        disabled={disabled} data-state={state} onClick={onToggle}>
        <Icon name="calendar" size={16} />
        <span className="od-datefield__value" aria-hidden="true" data-empty={value ? undefined : ''}>{value || placeholder}</span>
        <span id={id + '-value'} className="od-sr-only">{fullValue || value || placeholder}</span>
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
      </button>
      {error && <p role="alert" className="od-field-error"><Icon name="circle-alert" size={14} />{error}</p>}
    </div>
  );
}
