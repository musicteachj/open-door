import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { Tooltip } from './Tooltip.jsx';

export function PersonaSwitcher({ name, title, initials, onClick, forceTooltip, ...rest }) {
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
      <button type="button" className="od-persona__btn" onClick={onClick} aria-label={'Switch persona. Current: ' + name + ', ' + title} {...rest}>
        <span className="od-avatar" aria-hidden="true">{ini}</span>
        <span className="od-persona__text">
          <span className="od-persona__name od-truncate">{name}</span>
          <span ref={ref} className="od-persona__title od-truncate">{title}</span>
        </span>
        <Icon name="chevrons-up-down" size={16} style={{ color: 'var(--ink-muted)' }} />
      </button>
    </Tooltip>
  );
}
