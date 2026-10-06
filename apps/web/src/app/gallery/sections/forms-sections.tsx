import { useState } from 'react'
import { FilterSelect } from '@/components/forms/filter-select'
import { FilterToggle } from '@/components/forms/filter-toggle'
import { SearchField } from '@/components/forms/search-field'
import { Group, Section } from '../gallery-parts'

// The search field, filter select, and filter toggle in their states. The open select starts
// closed, with a trigger the test presses. Hover and focus are not shown: the tests hover and
// focus the real elements.

const LOCATIONS = [
  { id: 'austin', name: 'Austin warehouse', state: 'TX', count: 35 },
  { id: 'denver', name: 'Denver HQ', state: 'CO', count: 40 },
  { id: 'oakland', name: 'Oakland store', state: 'CA', count: 0 },
]

function Search({ initial, label }: { initial: string; label: string }) {
  const [value, setValue] = useState(initial)
  return <SearchField value={value} onChange={setValue} label={label} />
}

function Select({ initial, label, id }: { initial: string | null; label: string; id?: string }) {
  const [value, setValue] = useState<string | null>(initial)
  return (
    <FilterSelect id={id} label={label} value={value} options={LOCATIONS} onChange={setValue} />
  )
}

function Toggle({ initial }: { initial: boolean }) {
  const [pressed, setPressed] = useState(initial)
  return <FilterToggle count={44} pressed={pressed} onChange={setPressed} />
}

export function FormsSections() {
  return (
    <Group title="Search field, filter select, and filter toggle">
      <Section id="search-field-empty" title="Search field, empty">
        <Search initial="" label="Search the directory, empty" />
      </Section>
      <Section id="search-field-typed" title="Search field, typed (with Clear search)">
        <Search initial="Jordn" label="Search the directory, typed" />
      </Section>
      <Section id="filter-select-default" title="Filter select, All">
        <Select initial={null} label="Location" />
      </Section>
      <Section id="filter-select-active" title="Filter select, active (a location chosen)">
        <Select initial="denver" label="Location" />
      </Section>
      <Section id="filter-select-open" title="Filter select, open: press the trigger">
        <Select initial="denver" label="Location" id="filter-select-open-trigger" />
      </Section>
      <Section id="filter-toggle-off" title="Filter toggle, off">
        <Toggle initial={false} />
      </Section>
      <Section id="filter-toggle-on" title="Filter toggle, on">
        <Toggle initial />
      </Section>
    </Group>
  )
}
