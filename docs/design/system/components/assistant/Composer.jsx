import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { Button } from '../core/Button.jsx';
import { InlineError } from './InlineError.jsx';

export function Composer({
  value, defaultValue = '', onChange, onSubmit,
  placeholder = 'Ask about time off, pay, benefits, or policy…',
  disclosure = 'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.',
  submitLabel = 'Ask', rows = 3, error, onRetry, autoFocus, className = '', ...rest
}) {
  const [inner, setInner] = React.useState(defaultValue);
  const v = value !== undefined ? value : inner;
  const ref = React.useRef(null);
  const discId = React.useId();
  const change = (e) => { if (value === undefined) setInner(e.target.value); if (onChange) onChange(e.target.value, e); };
  const submit = (e) => {
    if (e) e.preventDefault();
    if (!v.trim()) { if (ref.current) ref.current.focus(); return; }
    if (onSubmit) onSubmit(v);
  };
  const keyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } };
  return (
    <form className={'od-composer-form ' + className} onSubmit={submit}>
      <div className="od-composer" {...rest}>
        <textarea ref={ref} className="od-composer__input" aria-label="Ask Open Door" aria-describedby={discId}
          rows={rows} value={v} onChange={change} onKeyDown={keyDown} placeholder={placeholder} autoFocus={autoFocus} />
        <div className="od-composer__footer">
          <p className="od-disclosure" id={discId}><Icon name="info" size={14} />{disclosure}</p>
          <Button type="submit" iconRight="arrow-right">{submitLabel}</Button>
        </div>
      </div>
      {error && <InlineError message={error} onRetry={onRetry || (() => onSubmit && onSubmit(v))} />}
    </form>
  );
}
