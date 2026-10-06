import React from 'react';

export function Tooltip({ content, open, disabled = false, className = '', children }) {
  const [hover, setHover] = React.useState(false);
  const id = React.useId();
  const shown = !disabled && (open !== undefined ? open : hover);
  const child = React.isValidElement(children) ? React.cloneElement(children, { 'aria-describedby': shown ? id : undefined }) : children;
  return (
    <span className={'od-tooltip-anchor ' + className}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)} onBlur={() => setHover(false)}
      onKeyDown={(e) => { if (e.key === 'Escape') setHover(false); }}>
      {child}
      {shown && <span role="tooltip" id={id} className="od-tooltip">{content}</span>}
    </span>
  );
}
