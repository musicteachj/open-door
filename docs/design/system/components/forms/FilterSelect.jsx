import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function FilterSelect({ label, value = null, options = [], allLabel, onChange, defaultOpen = false, className = '', ...rest }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const ref = React.useRef(null);
  const id = React.useId();
  React.useEffect(() => {
    if (!open) return undefined;
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', off);
    return () => document.removeEventListener('mousedown', off);
  }, [open]);
  const current = options.find((o) => o.value === value);
  const all = [{ value: null, label: allLabel || 'All', count: undefined }].concat(options);
  return (
    <div className={'od-filter ' + className} ref={ref} onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}>
      <button type="button" className="od-filter__trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={id}
        data-active={value != null} onClick={() => setOpen(!open)} {...rest}>
        <span className="od-filter__label">{label}</span>
        <span className="od-filter__value">{current ? current.label : 'All'}</span>
        <Icon name="chevron-down" size={16} className="od-filter__chev" />
      </button>
      {open && (
        <div className="od-filter__menu" role="listbox" id={id} aria-label={label}>
          {all.map((o) => (
            <button type="button" role="option" key={String(o.value)} aria-selected={o.value === value} className="od-filter__option"
              onClick={() => { onChange && onChange(o.value); setOpen(false); }}>
              <span className="od-filter__check">{o.value === value && <Icon name="check" size={16} strokeWidth={2} />}</span>
              <span className="od-filter__opt-label">{o.label}</span>
              {o.count != null && <span className="od-filter__count">{o.count}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
