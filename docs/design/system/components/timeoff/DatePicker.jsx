import React from 'react';
import { Icon } from '../core/Icon.jsx';

const pad = (n) => String(n).padStart(2, '0');
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const toKey = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
const fromKey = (k) => new Date(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8, 10));
const addDays = (k, n) => { const d = fromKey(k); d.setDate(d.getDate() + n); return toKey(d); };
const shiftMonth = (k, dm) => {
  const d = fromKey(k); const t = new Date(d.getFullYear(), d.getMonth() + dm, 1);
  t.setDate(Math.min(d.getDate(), new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate()));
  return toKey(t);
};

/** "Friday, October 30" from "2026-10-30". */
export function longDate(k) { const d = fromKey(k); return WEEKDAYS[d.getDay()] + ', ' + MONTHS[d.getMonth()] + ' ' + d.getDate(); }
/** "Fri, Oct 30" from "2026-10-30", for the Dates field. */
export function shortDate(k) { const d = fromKey(k); return WEEKDAYS[d.getDay()].slice(0, 3) + ', ' + MONTHS[d.getMonth()].slice(0, 3) + ' ' + d.getDate(); }

/** One day cell. Used by DatePicker; exported so specimens can show each state on its own. */
export function CalendarDay({ dayKey, off = false, holiday, today = false, selected = false, disabled = false, band, tabIndex = -1, tip = false, state, onSelect, onHover, onFocus }) {
  const label = longDate(dayKey) + (holiday ? ', ' + holiday + ', company holiday' : '') + (off ? ', not on your schedule' : '') + (today ? ', today' : '') + (disabled ? ', not available' : '');
  return (
    <div role="gridcell" className="od-cal__cell" data-band={band} aria-selected={selected || band === 'mid'}>
      <button type="button" className="od-cal__day" data-k={dayKey} tabIndex={tabIndex} aria-label={label}
        aria-disabled={disabled || undefined} data-off={off ? '' : undefined} data-today={today ? '' : undefined} data-selected={selected ? '' : undefined}
        data-state={state} onClick={() => !disabled && onSelect && onSelect(dayKey)} onMouseEnter={() => onHover && onHover(dayKey)} onFocus={() => onFocus && onFocus(dayKey)}>
        {+dayKey.slice(8)}
        {holiday && <span className="od-cal__dot" aria-hidden="true" />}
      </button>
      {holiday && tip && <span role="tooltip" className="od-cal__tip">{holiday + ', company holiday'}</span>}
    </div>
  );
}

export function DatePicker({
  id = 'cal', month, start, end, inProgress = false, hoverKey, focusKey, today, minKey, holidays = {}, workdays = [1, 2, 3, 4, 5],
  pastLabel = 'Past days can’t be picked for PTO',
  onSelect, onMonthChange, onFocusChange, onHoverChange, onDone, tipKey, stateKey, dayState
}) {
  const [y, m] = month;
  const root = React.useRef(null);
  const first = new Date(y, m, 1), count = new Date(y, m + 1, 0).getDate();
  const keys = Array.from({ length: count }, (_, i) => toKey(new Date(y, m, i + 1)));
  const lo = start, hi = end || (inProgress && hoverKey && start && hoverKey > start ? hoverKey : start);
  const inMonth = (k) => k && keys.includes(k);
  const tabKey = inMonth(focusKey) ? focusKey : inMonth(lo) ? lo : inMonth(today) ? today : keys.find((k) => !minKey || k >= minKey) || keys[0];
  const minDate = minKey ? fromKey(minKey) : null;
  const prevDisabled = !!minDate && y * 12 + m <= minDate.getFullYear() * 12 + minDate.getMonth();
  const focusDay = (k) => setTimeout(() => { const el = root.current && root.current.querySelector('[data-k="' + k + '"]'); if (el) el.focus(); }, 0);
  const onKey = (e) => {
    const k = e.target.getAttribute && e.target.getAttribute('data-k');
    if (!k) return;
    const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    let next = null;
    if (moves[e.key] != null) next = addDays(k, moves[e.key]);
    else if (e.key === 'PageUp' || e.key === 'PageDown') next = shiftMonth(k, e.key === 'PageUp' ? -1 : 1);
    else if (e.key === 'Home') next = addDays(k, -fromKey(k).getDay());
    else if (e.key === 'End') next = addDays(k, 6 - fromKey(k).getDay());
    else if (e.key === 'Escape') { e.preventDefault(); if (onDone) onDone(); return; }
    if (!next) return;
    e.preventDefault();
    const d = fromKey(next);
    if (d.getMonth() !== m || d.getFullYear() !== y) onMonthChange && onMonthChange([d.getFullYear(), d.getMonth()]);
    if (onFocusChange) onFocusChange(next);
    if (inProgress && onHoverChange) onHoverChange(next);
    focusDay(next);
  };
  const cells = [];
  for (let i = 0; i < first.getDay(); i++) cells.push(null);
  keys.forEach((k) => cells.push(k));
  while (cells.length % 7) cells.push(null);
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  const range = lo && hi && lo !== hi;
  const hint = inProgress ? 'Now pick the last day. For one day, choose Done.'
    : start ? 'Selected: ' + (end && end !== start ? shortDate(start) + ' to ' + shortDate(end) : shortDate(start)) : 'Pick a day, or a first and last day.';
  return (
    <div className="od-cal" id={id} ref={root}>
      <div className="od-cal__head">
        <h3 id={id + '-title'} className="od-cal__title" aria-live="polite">{MONTHS[m] + ' ' + y}</h3>
        <div className="od-cal__nav">
          <button type="button" className="od-icon-btn" aria-label="Previous month" disabled={prevDisabled} onClick={() => onMonthChange && onMonthChange([m === 0 ? y - 1 : y, (m + 11) % 12])}><Icon name="chevron-left" size={16} /></button>
          <button type="button" className="od-icon-btn" aria-label="Next month" onClick={() => onMonthChange && onMonthChange([m === 11 ? y + 1 : y, (m + 1) % 12])}><Icon name="chevron-right" size={16} /></button>
        </div>
      </div>
      <div role="grid" aria-labelledby={id + '-title'} onKeyDown={onKey} onMouseLeave={() => onHoverChange && onHoverChange(null)}>
        <div role="row" className="od-cal__row">
          {WEEKDAYS.map((w) => <span key={w} role="columnheader" aria-label={w} className="od-cal__wd">{w.slice(0, 2)}</span>)}
        </div>
        {weeks.map((wk, wi) => (
          <div role="row" className="od-cal__row" key={wi}>
            {wk.map((k, di) => {
              if (!k) return <div role="gridcell" className="od-cal__cell" key={di} />;
              const mid = range && k > lo && k < hi;
              return (
                <CalendarDay key={k} dayKey={k} off={!workdays.includes(fromKey(k).getDay())} holiday={holidays[k]} today={k === today}
                  selected={!!lo && (k === lo || k === hi)} disabled={!!minKey && k < minKey}
                  band={!range ? undefined : mid ? 'mid' : k === lo ? 'start' : k === hi ? 'end' : undefined}
                  tabIndex={k === tabKey ? 0 : -1} tip={tipKey === k || hoverKey === k} state={stateKey === k ? dayState : undefined}
                  onSelect={onSelect} onHover={onHoverChange} onFocus={onFocusChange} />
              );
            })}
          </div>
        ))}
      </div>
      <div className="od-cal__legend">
        <span><span className="od-cal__sw od-cal__sw--off" aria-hidden="true" />Not on your schedule</span>
        <span><span className="od-cal__sw od-cal__sw--hol" aria-hidden="true" />Company holiday</span>
        <span><span className="od-cal__sw od-cal__sw--today" aria-hidden="true" />Today</span>
        <span><span className="od-cal__sw od-cal__sw--past" aria-hidden="true">8</span>{pastLabel}</span>
      </div>
      <div className="od-cal__foot">
        <p role="status" className="od-cal__hint">{hint}</p>
        <button type="button" className="od-btn od-btn--secondary od-btn--sm" onClick={onDone}>Done</button>
      </div>
    </div>
  );
}
