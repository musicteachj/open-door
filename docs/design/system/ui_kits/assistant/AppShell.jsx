import React from 'react';
import { Logo } from '../../components/core/Logo.jsx';
import { NavItem } from '../../components/navigation/NavItem.jsx';
import { PersonaSwitcher } from '../../components/navigation/PersonaSwitcher.jsx';

const NAV = [
  { id: 'ask', icon: 'message-circle', label: 'Ask', href: '#ask' },
  { id: 'time-off', icon: 'calendar', label: 'Time off', href: '#time-off' },
  { id: 'directory', icon: 'users', label: 'Directory', href: '#directory' },
  { id: 'handbook', icon: 'book-open', label: 'Handbook', href: '#handbook' }
];

export function AppShell({ current = 'ask', persona, children }) {
  return (
    <div className="kit-app">
      <aside className="kit-sidebar">
        <div className="kit-logo"><Logo org="Juniper Row" /></div>
        <nav className="od-nav" aria-label="Main">
          {NAV.map((n) => <NavItem key={n.id} icon={n.icon} label={n.label} href={n.href} current={n.id === current} />)}
        </nav>
        <div className="kit-spacer"></div>
        <PersonaSwitcher name={persona.name} title={persona.title} />
      </aside>
      <main className="kit-main">{children}</main>
    </div>
  );
}
