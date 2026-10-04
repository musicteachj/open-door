import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function GlanceLink({ value, caption, destination, href = '#', marker = false, className = '', ...rest }) {
  return (
    <a href={href} className={'od-glance-link ' + className} aria-label={value + ' ' + caption + '. Open ' + destination} {...rest}>
      <span className="od-glance-link__body">
        <span className="od-glance-link__value-row">
          <span className="od-glance-link__value">{value}</span>
          {marker && <span className="od-marker" aria-hidden="true" />}
        </span>
        <span className="od-glance-link__caption">{caption}</span>
      </span>
      <span className="od-glance-link__dest">{destination}<Icon name="chevron-right" size={16} /></span>
    </a>
  );
}
