import React from 'react';

export function ChoiceGroup({ id = 'choice', label, options = [], value, onChange, disabled = false }) {
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
      {label && <span id={id + '-label'} className="od-field-label">{label}</span>}
      <div role="radiogroup" aria-labelledby={label ? id + '-label' : undefined} className="od-choice" onKeyDown={onKey}>
        {options.map((o, i) => {
          const on = o.value === value;
          return (
            <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={on}
              tabIndex={on ? 0 : -1} disabled={disabled} className="od-choice__opt" data-state={o.state}
              onClick={() => onChange && onChange(o.value)}>
              <span className="od-choice__radio" aria-hidden="true" />
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
