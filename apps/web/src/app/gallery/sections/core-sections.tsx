import { EmptyState } from '@/components/core/empty-state'
import { Logo } from '@/components/core/logo'
import { PageHeader } from '@/components/core/page-header'
import { GlanceLink } from '@/components/status/glance-link'
import { GlanceList, type GlanceItem } from '@/components/status/glance-list'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { Group, Section } from '../gallery-parts'

// The core and status components, each state under a heading with a stable id. Hover and focus
// are not shown: the tests hover and focus the real elements.

const GLANCE_ITEMS: GlanceItem[] = [
  {
    id: 'pto',
    value: '11.5',
    label: 'days PTO available',
    destination: 'Time off',
    to: '/gallery',
  },
  {
    id: 'pending',
    value: '1',
    label: 'request pending',
    destination: 'Approvals',
    to: '/gallery',
    marker: true,
  },
]

export function CoreSections() {
  return (
    <>
      <Group title="Logo">
        <Section id="logo-default" title="Logo, before sign-in">
          <Logo />
        </Section>
        <Section id="logo-customer" title="Logo, with the customer's name">
          <Logo customerName="Juniper Row" />
        </Section>
      </Group>
      <Group title="Page header">
        <Section id="page-header-title" title="Page header, title">
          <PageHeader title="Directory" />
        </Section>
        <Section id="page-header-count" title="Page header, title with a count and a right slot">
          <PageHeader
            title="Directory"
            count="44 of 120 people"
            right={<SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>}
          />
        </Section>
        <Section id="page-header-back" title="Page header, back link">
          <PageHeader
            back={{ to: '/gallery', label: 'Directory' }}
            right={<SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>}
          />
        </Section>
      </Group>
      <Group title="Empty state">
        <Section id="empty-state-action" title="Empty state, with an action">
          <EmptyState
            message="No one matches these filters."
            action={{ label: 'Clear filters', onAction: () => {} }}
          />
        </Section>
        <Section id="empty-state-message" title="Empty state, message only">
          <EmptyState message="Nothing here yet." />
        </Section>
      </Group>
      <Group title="Sandbox indicator">
        <Section id="sandbox-indicator-default" title="Sandbox indicator, default">
          <SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>
        </Section>
      </Group>
      <Group title="At-a-glance link and list">
        <Section id="glance-link-default" title="At-a-glance link, default">
          <div className="w-80">
            <GlanceLink
              value="11.5"
              label="days PTO available"
              destination="Time off"
              to="/gallery"
            />
          </div>
        </Section>
        <Section id="glance-link-marker" title="At-a-glance link, with a marker">
          <div className="w-80">
            <GlanceLink
              value="1"
              label="request pending"
              destination="Approvals"
              to="/gallery"
              marker
            />
          </div>
        </Section>
        <Section id="glance-list-default" title="At-a-glance list">
          <div className="w-80">
            <GlanceList items={GLANCE_ITEMS} />
          </div>
        </Section>
      </Group>
    </>
  )
}
