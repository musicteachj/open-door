import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { Tooltip } from './Tooltip.jsx';

export function PersonaSwitcher({ name, title, initials, onClick, forceTooltip, expanded, busyLabel, ...rest }) {
  const ref = React.useRef(null);
  const [truncated, setTruncated] = React.useState(false);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const check = () => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const textW = range.getBoundingClientRect().width;
      setTruncated(el.scrollWidth > el.clientWidth || textW > el.getBoundingClientRect().width + 0.5);
    };
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [title]);
  const ini = initials || name.split(' ').map((w) => w[0]).join('').slice(0, 2);
  return (
    <Tooltip content={title} disabled={!truncated} open={forceTooltip} className="od-persona">
      <button type="button" className="od-persona__btn" onClick={onClick} aria-haspopup="menu" aria-expanded={!!expanded} aria-busy={!!busyLabel}
        data-open={expanded ? 'true' : undefined} aria-label={busyLabel || ('Switch persona. Current: ' + name + ', ' + title)} {...rest}>
        {busyLabel ? (
          <>
            <span className="od-persona__spin"><Icon name="loader-circle" size={16} strokeWidth={2} className="od-spin" style={{ color: 'var(--primary)' }} /></span>
            <span className="od-persona__busy">{busyLabel}</span>
          </>
        ) : (
          <>
            <span className="od-avatar" aria-hidden="true">{ini}</span>
            <span className="od-persona__text">
              <span className="od-persona__name od-truncate">{name}</span>
              <span ref={ref} className="od-persona__title od-truncate">{title}</span>
            </span>
            <Icon name="chevrons-up-down" size={16} style={{ color: 'var(--ink-muted)' }} />
          </>
        )}
      </button>
    </Tooltip>
  );
}
