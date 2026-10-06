import { ClipboardCheck, MessageCircle, Users } from 'lucide-react'
import { useState } from 'react'
import { NavItem } from '@/components/navigation/nav-item'
import { PersonaMenu, type PersonaOption } from '@/components/navigation/persona-menu'
import { PersonaSwitcher } from '@/components/navigation/persona-switcher'
import { Group, Section } from '../gallery-parts'

// The navigation components, each state under a heading with a stable id. Hover and focus are not
// shown: the tests hover and focus the real elements. The menu starts closed, with its switcher as
// the trigger, like the app shell's.

const PERSONAS: PersonaOption[] = [
  { key: 'priya', name: 'Priya Raman', title: 'Visual Merchandiser' },
  { key: 'mateo', name: 'Mateo Cruz', title: 'Store Associate' },
  { key: 'marcus', name: 'Marcus Bell', title: 'Department Lead, Apparel' },
  { key: 'dana', name: 'Dana Ortiz', title: 'HR Business Partner' },
]

function Menu() {
  const [currentKey, setCurrentKey] = useState('priya')
  return (
    <PersonaMenu
      personas={PERSONAS}
      currentKey={currentKey}
      onSwitch={setCurrentKey}
      onSignOut={() => {}}
    />
  )
}

export function NavigationSections() {
  return (
    <>
      <Group title="Nav item">
        <Section id="nav-item-default" title="Nav item, default">
          <div className="w-sidebar">
            <NavItem icon={Users} label="Directory" to="/gallery" current={false} />
          </div>
        </Section>
        <Section id="nav-item-current" title="Nav item, current">
          <div className="w-sidebar">
            <NavItem icon={MessageCircle} label="Ask" to="/gallery" current />
          </div>
        </Section>
        <Section id="nav-item-count" title="Nav item, with a count">
          <div className="w-sidebar">
            <NavItem
              icon={ClipboardCheck}
              label="Approvals"
              to="/gallery"
              count={1}
              current={false}
            />
          </div>
        </Section>
        <Section id="nav-item-count-current" title="Nav item, current with a count">
          <div className="w-sidebar">
            <NavItem icon={ClipboardCheck} label="Approvals" to="/gallery" count={3} current />
          </div>
        </Section>
      </Group>
      <Group title="Persona switcher">
        <Section id="persona-switcher-closed" title="Persona switcher, closed">
          <div className="w-sidebar">
            <PersonaSwitcher name="Priya Raman" title="Visual Merchandiser" />
          </div>
        </Section>
        <Section
          id="persona-switcher-truncated"
          title="Persona switcher, truncated title with a tooltip"
        >
          <div className="w-sidebar">
            <PersonaSwitcher
              id="persona-switcher-truncated-button"
              name="Marcus Bell"
              title="Senior Department Lead, Apparel and Accessories, West Region"
            />
          </div>
        </Section>
        <Section id="persona-switcher-switching" title="Persona switcher, switching">
          <div className="w-sidebar">
            <PersonaSwitcher
              name="Priya Raman"
              title="Visual Merchandiser"
              busyLabel="Switching to Marcus…"
            />
          </div>
        </Section>
      </Group>
      <Group title="Persona menu">
        <Section id="persona-menu-open" title="Persona menu, open: press the switcher">
          <div id="persona-menu-anchor" className="w-sidebar">
            <Menu />
          </div>
        </Section>
      </Group>
    </>
  )
}
