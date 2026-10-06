import React from 'react';

export function GlanceList({ label = 'At a glance', className = '', children }) {
  const id = React.useId();
  return (
    <section className={'od-glance ' + className} aria-labelledby={id}>
      <h2 className="od-glance__label" id={id}>{label}</h2>
      <div className="od-glance">{children}</div>
    </section>
  );
}
