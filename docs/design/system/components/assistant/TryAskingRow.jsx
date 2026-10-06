import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function TryAskingRow({ question, onSelect, className = '', ...rest }) {
  return (
    <button type="button" className={'od-try-row ' + className} onClick={() => onSelect && onSelect(question)} {...rest}>
      <span>{question}</span>
      <Icon name="arrow-right" size={16} />
    </button>
  );
}
