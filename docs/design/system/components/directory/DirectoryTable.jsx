import React from 'react';
import { DirectoryRow } from './DirectoryRow.jsx';
import { SkeletonRow } from './SkeletonRow.jsx';
import { Button } from '../core/Button.jsx';

export function DirectoryTable({ people = [], total, loading = false, shown = 50, onShowMore, onOpen, youId, query = '', onClear, clearLabel }) {
  const count = total != null ? total : people.length;
  return (
    <div aria-busy={loading}>
      <div className="od-dir-cols od-dir-head" aria-hidden="true"><span>Name</span><span>Title</span><span>Department</span><span>Location</span><span></span></div>
      {loading && <>{[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <SkeletonRow key={i} variant={i} />)}<span className="od-sr-only">Loading the directory</span></>}
      {!loading && people.length > 0 && (
        <div role="list" aria-label="People">
          {people.slice(0, shown).map((p) => (
            <DirectoryRow key={p.id} name={p.name} title={p.title} department={p.department} location={p.location}
              href={p.href} isYou={p.id === youId} onOpen={onOpen ? () => onOpen(p) : undefined} />
          ))}
        </div>
      )}
      {!loading && people.length === 0 && (
        <div className="od-dir-empty" role="status">
          <p className="od-dir-empty__text">{query ? 'No one matches \u201C' + query + '\u201D.' : 'No one matches these filters.'}</p>
          {onClear && <Button variant="secondary" onClick={onClear}>{clearLabel || (query ? 'Clear search' : 'Clear filters')}</Button>}
        </div>
      )}
      {!loading && people.length > shown && (
        <div className="od-dir-more"><span>Showing {shown} of {count}</span><Button variant="secondary" onClick={onShowMore}>Show more</Button></div>
      )}
      {!loading && people.length > 50 && shown >= people.length && <div className="od-dir-more">Showing all {count}</div>}
    </div>
  );
}
