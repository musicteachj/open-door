import React from 'react';

export function LastUpdated({ date, bare = false, className = '' }) {
  return <span className={'od-updated ' + className}>{bare ? date : 'Last updated ' + date}</span>;
}
