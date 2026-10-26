import { useState } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { Toast, ToastProvider, ToastViewport } from '@/components/ui/toast'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { marker } from './gallery-marker.json'
import { Group, Section } from './gallery-parts'
import { AssistantSections } from './sections/assistant-sections'
import { DirectorySections } from './sections/directory-sections'
import { FeedbackSections } from './sections/feedback-sections'
import { HandbookSections } from './sections/handbook-sections'
import { FormsSections } from './sections/forms-sections'
import { ConversationSections } from './sections/conversation-sections'
import { CoreSections } from './sections/core-sections'
import { LandingSections } from './sections/landing-sections'
import { NavigationSections } from './sections/navigation-sections'
import { ApprovalsSections } from './sections/approvals-sections'
import { ConfirmCardSections } from './sections/confirm-card-sections'
import { TimeOffSections } from './sections/timeoff-sections'

// Every primitive in every state it has, for the browser tests and for looking at. The route is
// compiled in only for development and the e2e build (router.tsx), and the build check
// (scripts/check-no-gallery.mjs) fails if this page's marker text (gallery-marker.json, which the
// heading and the check share) reaches a production build.
// Hover and focus are not shown here: the tests hover and focus the real elements.
//
// Each state sits under a heading with a stable id, so a test can address it. The overlays
// (select, menu, tooltip, toast) start closed, with a trigger the test presses.

const VARIANTS = ['primary', 'secondary', 'ghost', 'destructive'] as const

function Buttons() {
  return (
    <Group title="Button">
      {VARIANTS.map((variant) => (
        <div key={variant} className="flex flex-col gap-4">
          <Section id={`button-${variant}-default`} title={`${variant}, default`}>
            <Button variant={variant}>Label</Button>
            <Button variant={variant} size="sm">
              Label
            </Button>
          </Section>
          <Section id={`button-${variant}-disabled`} title={`${variant}, disabled`}>
            <Button variant={variant} disabled>
              Label
            </Button>
            <Button variant={variant} size="sm" disabled>
              Label
            </Button>
          </Section>
          <Section id={`button-${variant}-loading`} title={`${variant}, loading`}>
            <Button variant={variant} loading>
              Label
            </Button>
          </Section>
        </div>
      ))}
    </Group>
  )
}

function Fields() {
  return (
    <Group title="Input and textarea">
      <Section id="input-default" title="Input, empty with placeholder">
        <Input aria-label="Search people" placeholder="Search people" />
      </Section>
      <Section id="input-filled" title="Input, filled">
        <Input aria-label="Name" defaultValue="Priya Raman" />
      </Section>
      <Section id="input-invalid" title="Input, invalid">
        <Input aria-label="Email" defaultValue="priya@" aria-invalid="true" />
      </Section>
      <Section id="input-disabled" title="Input, disabled">
        <Input aria-label="Employee ID" defaultValue="E-1042" disabled />
      </Section>
      <Section id="textarea-default" title="Textarea, empty with placeholder">
        <Textarea aria-label="Message" placeholder="Ask a question" />
      </Section>
      <Section id="textarea-disabled" title="Textarea, disabled">
        <Textarea aria-label="Notes" defaultValue="Locked" disabled />
      </Section>
    </Group>
  )
}

const LOCATIONS = ['San Francisco', 'Denver', 'Austin']

function Selects() {
  return (
    <Group title="Select">
      <Section id="select-placeholder" title="Select, placeholder (closed)">
        <Select>
          <SelectTrigger id="select-placeholder-trigger" aria-label="Location">
            <SelectValue placeholder="All locations" />
          </SelectTrigger>
          <SelectContent>
            {LOCATIONS.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>
      <Section id="select-chosen" title="Select, with a choice">
        <Select defaultValue="Denver">
          <SelectTrigger aria-label="Office">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LOCATIONS.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>
      <Section id="select-disabled" title="Select, disabled">
        <Select disabled>
          <SelectTrigger aria-label="Department">
            <SelectValue placeholder="All departments" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="people">People</SelectItem>
          </SelectContent>
        </Select>
      </Section>
      <Section id="select-open" title="Select, open: press the trigger">
        <Select defaultValue="Denver">
          <SelectTrigger id="select-open-trigger" aria-label="Location choices">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LOCATIONS.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
            <SelectItem value="closed" disabled>
              Remote
            </SelectItem>
          </SelectContent>
        </Select>
      </Section>
    </Group>
  )
}

function Menu() {
  const [who, setWho] = useState('priya')
  return (
    <Group title="Dropdown menu">
      <Section id="menu-open" title="Menu, open: press the trigger">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button id="menu-open-trigger" variant="secondary">
              Persona menu
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Signed in as</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup value={who} onValueChange={setWho}>
              <DropdownMenuRadioItem value="priya">Priya Raman</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="marcus">Marcus Bell</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </Section>
    </Group>
  )
}

function Tooltips() {
  return (
    <Group title="Tooltip">
      <Section id="tooltip-trigger-section" title="Tooltip, on keyboard focus or hover">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button id="tooltip-trigger" variant="secondary">
              Senior Staff Accountant, Finance
            </Button>
          </TooltipTrigger>
          <TooltipContent>Senior Staff Accountant, Finance and Operations</TooltipContent>
        </Tooltip>
      </Section>
    </Group>
  )
}

function Toasts() {
  const [open, setOpen] = useState(false)
  return (
    <Group title="Toast">
      <Section id="toast-section" title="Toast: press the button">
        <Button id="toast-show" variant="secondary" onClick={() => setOpen(true)}>
          Show a toast
        </Button>
        <Toast id="toast-example" open={open} onOpenChange={setOpen}>
          Saved your changes.
        </Toast>
      </Section>
    </Group>
  )
}

function Avatars() {
  return (
    <Group title="Avatar">
      <Section id="avatar-md" title="Avatar, list size">
        <Avatar aria-hidden="true">
          <AvatarFallback>PR</AvatarFallback>
        </Avatar>
      </Section>
      <Section id="avatar-sm" title="Avatar, menu size">
        <Avatar size="sm" aria-hidden="true">
          <AvatarFallback>MB</AvatarFallback>
        </Avatar>
      </Section>
    </Group>
  )
}

function Skeletons() {
  return (
    <Group title="Skeleton">
      <Section id="skeleton-default" title="Skeleton, bar and avatar">
        <Skeleton className="w-48" />
        <Skeleton className="size-9 rounded-full" />
      </Section>
    </Group>
  )
}

export function Gallery() {
  return (
    <ToastProvider>
      <main className="mx-auto flex max-w-content flex-col gap-8 p-8 text-ink">
        <h1 className="text-h1 font-semibold">{marker}</h1>
        <p className="text-body text-ink-muted">
          Every primitive in every state. Development and test builds only.
        </p>
        <Buttons />
        <Fields />
        <Selects />
        <Menu />
        <Tooltips />
        <Toasts />
        <Avatars />
        <Skeletons />
        <CoreSections />
        <NavigationSections />
        <FeedbackSections />
        <AssistantSections />
        <ConversationSections />
        <LandingSections />
        <FormsSections />
        <DirectorySections />
        <HandbookSections />
        <TimeOffSections />
        <ApprovalsSections />
        <ConfirmCardSections />
      </main>
      <ToastViewport />
    </ToastProvider>
  )
}
