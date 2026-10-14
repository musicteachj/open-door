import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function CitedPassage({ children, onClear, compact = false, autoFocus = false, id = 'cited-passage', className = '' }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (autoFocus && ref.current) { ref.current.scrollIntoView({ block: 'center' }); ref.current.focus({ preventScroll: true }); }
  }, [autoFocus]);
  return (
    <div ref={ref} role="region" aria-labelledby={id} tabIndex={-1} className={'od-cited ' + (compact ? 'od-cited--compact ' : '') + className}>
      <div className="od-cited__head">
        <span id={id} className="od-cited__label"><Icon name="quote" size={16} />Cited passage</span>
        {onClear && <button type="button" className="od-cited__clear" onClick={onClear}><Icon name="x" size={14} />Clear highlight</button>}
      </div>
      <p className="od-cited__text">{children}</p>
    </div>
  );
}
