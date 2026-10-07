import React from 'react';

export function SourcesBlock({ sources = [], className = '' }) {
  return (
    <div className={'od-sources ' + className}>
      <h2 className="od-sources__title">Sources</h2>
      {sources.map((s) => <p key={s} className="od-sources__item">{s}</p>)}
    </div>
  );
}
