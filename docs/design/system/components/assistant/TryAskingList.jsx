import React from 'react';
import { TryAskingRow } from './TryAskingRow.jsx';

export function TryAskingList({ label = 'Try asking', questions = [], onSelect, className = '' }) {
  const id = React.useId();
  return (
    <section className={'od-try ' + className} aria-labelledby={id}>
      <h2 className="od-try__label" id={id}>{label}</h2>
      <div className="od-try__grid">
        {questions.map((q) => <TryAskingRow key={q} question={q} onSelect={onSelect} />)}
      </div>
    </section>
  );
}
