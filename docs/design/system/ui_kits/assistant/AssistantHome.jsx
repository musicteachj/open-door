import React from 'react';
import { Composer } from '../../components/assistant/Composer.jsx';
import { TryAskingList } from '../../components/assistant/TryAskingList.jsx';
import { GlanceList } from '../../components/status/GlanceList.jsx';
import { GlanceLink } from '../../components/status/GlanceLink.jsx';
import { SandboxIndicator } from '../../components/status/SandboxIndicator.jsx';

const QUESTIONS = ['How many sick days do I get?', 'Book next Friday off', 'What holidays do we have this year?', 'Who do I talk to about a concern?'];

function partOfDay() {
  const h = new Date().getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}

export function AssistantHome({ firstName, sandboxHours = 21 }) {
  const [q, setQ] = React.useState('');
  const [error, setError] = React.useState(null);
  // The answer view isn't designed yet, so sending shows the error state; Retry clears it.
  const send = () => setError('Something went wrong sending that.');
  return (
    <div className="kit-sheet">
      <section className="kit-content">
        <h1 className="kit-greeting">Good {partOfDay()}, {firstName}.</h1>
        <Composer value={q} onChange={(v) => { setQ(v); setError(null); }} onSubmit={send} error={error} onRetry={() => setError(null)} />
        <div className="kit-try"><TryAskingList questions={QUESTIONS} onSelect={(v) => { setQ(v); setError(null); }} /></div>
      </section>
      <aside className="kit-rail" aria-label="Your summary">
        <div className="kit-rail__top"><SandboxIndicator hours={sandboxHours} /></div>
        <div className="kit-rail__glance">
          <GlanceList>
            <GlanceLink value="11.5" caption="days PTO available" destination="Time off" href="#time-off" />
            <GlanceLink value="1" caption="request pending" destination="Time off" href="#time-off" marker />
            <GlanceLink value="Sep 12" caption="Handbook updated" destination="Handbook" href="#handbook" />
          </GlanceList>
        </div>
      </aside>
    </div>
  );
}
