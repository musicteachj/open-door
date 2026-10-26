import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { Button } from '../core/Button.jsx';
import { Avatar } from '../core/Avatar.jsx';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';
import { PreviewBlock } from '../timeoff/PreviewBlock.jsx';
import { FormMessage } from '../timeoff/FormMessage.jsx';
import { NoteField } from '../approvals/NoteField.jsx';

const ENDED = {
  dismissed: 'You dismissed this. Nothing was changed.',
  replaced: 'Replaced by a newer card. Nothing was changed.',
  expired: 'This card expired after 15 minutes. Nothing was changed.'
};

/** A proposed time-off action in the conversation. Nothing happens until the person confirms. */
export function ConfirmCard({
  id = 'cc', title, icon = 'calendar-plus', state = 'pending', expires = 'Expires at 3:42 PM',
  who, facts = [], preview, coverage, info, warning, note, onNoteChange, sources = [],
  confirmLabel = 'Confirm', confirmAria, dismissAria, onConfirm, onDismiss, onAskAgain,
  executedText, executedLink, badge, failedText, confirmState, dismissState
}) {
  const pending = state === 'pending' || state === 'streaming' || state === 'confirming';
  const muted = state === 'failed' || !!ENDED[state];
  const busy = state === 'confirming';
  return (
    <section className="od-confirm" data-state={state} data-muted={muted ? '' : undefined} aria-labelledby={id + '-t'}>
      <div className="od-confirm__head">
        <span className="od-confirm__title"><span className="od-confirm__tile" aria-hidden="true"><Icon name={icon} size={18} /></span><h3 id={id + '-t'}>{title}</h3></span>
        {pending && <span className="od-confirm__exp"><Icon name="clock" size={14} />{expires}</span>}
        {state === 'executed' && badge && <StatusBadge status={badge} />}
      </div>
      <div className="od-confirm__body">
        {who && <div className="od-confirm__who"><Avatar initials={who.initials} muted={muted} /><span><span className="od-confirm__who-name">{who.name}</span><span className="od-confirm__who-title">{who.title}</span></span></div>}
        <dl className="od-confirm__facts">
          {facts.map((f) => <React.Fragment key={f.label}><dt>{f.label}</dt><dd data-strong={f.label === 'Dates' ? '' : undefined}>{f.badge ? <StatusBadge status={f.badge} /> : f.value}</dd></React.Fragment>)}
        </dl>
        {preview && <PreviewBlock id={id + '-pv'} {...preview} sources={sources} />}
        {coverage && <div className="od-confirm__cov"><Icon name="users" size={16} /><div><span>Team coverage</span><span>{coverage}</span></div></div>}
        {info && <p className="od-confirm__info"><Icon name="info" size={16} />{info}</p>}
        {warning && pending && <FormMessage tone="warning">{warning}</FormMessage>}
        {onNoteChange && pending && <NoteField id={id + '-note'} label={'Note to ' + who.name.split(' ')[0] + ' (optional)'} helper={who.name.split(' ')[0] + ' will see this note. Up to 300 characters.'} value={note || ''} onChange={onNoteChange} disabled={busy} />}
        {state === 'executed' && note && note.trim() && <div className="od-confirm__note"><span>Your note</span><p>“{note.trim()}”</p></div>}
        {!preview && sources.length > 0 && <div className="od-preview__sources"><span>Sources</span>{sources.map((s) => <a key={s.label} className="od-source-chip" href={s.href} aria-label={'Source: ' + s.label.replace(' · ', ', ')}><Icon name="book-open" size={13} />{s.label}</a>)}</div>}
      </div>
      {pending && (
        <div className="od-confirm__foot">
          <p className="od-confirm__proposed"><span aria-hidden="true" className="od-confirm__ai">AI</span>Proposed by the AI. Nothing happens until you confirm.</p>
          <div className="od-confirm__actions">
            <Button loading={busy} disabled={state === 'streaming'} aria-disabled={state === 'streaming' || undefined} aria-label={busy ? undefined : confirmAria} aria-describedby={state === 'streaming' ? id + '-wait' : undefined} onClick={onConfirm} data-state={confirmState}>{busy ? 'Confirming…' : confirmLabel}</Button>
            <Button variant="secondary" disabled={busy} aria-label={dismissAria} onClick={onDismiss} data-state={dismissState}>Dismiss</Button>
            {state === 'streaming' && <span id={id + '-wait'} className="od-confirm__wait">Wait for the answer to finish</span>}
          </div>
        </div>
      )}
      {state === 'executed' && <div role="status" tabIndex={-1} className="od-confirm__done"><Icon name="circle-check" size={18} /><p>{executedText}</p>{executedLink && <a href={executedLink.href}>{executedLink.label}</a>}</div>}
      {state === 'failed' && <div role="alert" tabIndex={-1} className="od-confirm__fail"><Icon name="circle-alert" size={18} /><p>{failedText}</p></div>}
      {ENDED[state] && <div role="status" tabIndex={-1} className="od-confirm__ended"><Icon name="ban" size={18} /><p>{ENDED[state]}</p>{state === 'expired' && <Button variant="secondary" size="sm" icon="rotate-ccw" onClick={onAskAgain}>Ask again</Button>}</div>}
    </section>
  );
}
