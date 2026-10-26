import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function HoursStepper({ id = 'hours', label = 'Hours', value = '1', min = 1, max = 8, hint = '1 to 8 hours', error, disabled = false, onChange, 'data-state': state }) {
  const n = parseInt(value, 10);
  const set = (v) => onChange && onChange(String(Math.max(min, Math.min(max, v))));
  return (
    <div className="od-field" style={{ gap: 6 }}>
      <label htmlFor={id} className="od-field-label">{label}</label>
      <div className="od-stepper-row">
        <div className="od-stepper" data-invalid={error ? '' : undefined} data-disabled={disabled ? '' : undefined} data-state={state}>
          <button type="button" className="od-stepper__btn" aria-label="Fewer hours" disabled={disabled || !(n > min)} onClick={() => set(n - 1)}><Icon name="minus" size={16} /></button>
          <input id={id} className="od-stepper__input" type="text" inputMode="numeric" value={value} disabled={disabled}
            aria-invalid={error ? true : undefined} aria-describedby={id + '-hint'} onChange={(e) => onChange && onChange(e.target.value.slice(0, 2))} />
          <button type="button" className="od-stepper__btn" aria-label="More hours" disabled={disabled || !(n < max)} onClick={() => set((n || 0) + 1)}><Icon name="plus" size={16} /></button>
        </div>
        <span id={id + '-hint'} className="od-field-hint">{hint}</span>
      </div>
      {error && <p role="alert" className="od-field-error"><Icon name="circle-alert" size={14} />{error}</p>}
    </div>
  );
}
