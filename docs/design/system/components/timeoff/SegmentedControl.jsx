import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function SegmentedControl({ id = 'seg', label, options = [], value, onChange, disabled = false }) {
  const refs = React.useRef([]);
  const onKey = (e) => {
    const i = options.findIndex((o) => o.value === value);
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const n = (i + step + options.length) % options.length;
    if (onChange) onChange(options[n].value);
    if (refs.current[n]) refs.current[n].focus();
  };
  return (
    <div className="od-field">
      <span id={id + '-label'} className="od-field-label">{label}</span>
      <div role="radiogroup" aria-labelledby={id + '-label'} className="od-seg" onKeyDown={onKey}>
        {options.map((o, i) => {
          const on = o.value === value;
          return (
            <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={on}
              tabIndex={on ? 0 : -1} disabled={disabled} className="od-seg__opt" data-state={o.state}
              onClick={() => onChange && onChange(o.value)}>
              {on && <Icon name="check" size={14} strokeWidth={2.25} />}
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
