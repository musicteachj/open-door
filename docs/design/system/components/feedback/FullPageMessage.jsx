import React from 'react';

export function FullPageMessage({ title, body, reference, children, className = '' }) {
  return (
    <div className={'od-fullpage ' + className}>
      <div className="od-fullpage__inner">
        <h1 className="od-fullpage__title">{title}</h1>
        {body && <p className="od-fullpage__body">{body}</p>}
        {reference && <p className="od-fullpage__ref">Reference<code>{reference}</code></p>}
        {children && <div className="od-fullpage__actions">{children}</div>}
      </div>
    </div>
  );
}
