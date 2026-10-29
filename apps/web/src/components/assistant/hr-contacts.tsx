import { Users } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'
import type { HrContactOut } from '@/api/generated'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'
import { APP_LINK } from './link-class'
import type { PageLink } from '@/lib/page-link'
import { HR_SHARED_INBOX, conversationCopy } from './labels'

type HrContactsProps = {
  /** HR people from the directory: the API sends a title and an office, either of which can be null. */
  contacts: HrContactOut[]
  /**
   * `inline` sits inside an escalation panel, which supplies the border. `card` is the standalone
   * bordered card under a not-found answer.
   */
  variant?: 'inline' | 'card'
  /**
   * Adds this link ("Write to HR") after the contacts. No default: the page passes
   * `WRITE_TO_HR_LINK`, or nothing. HR has no My cases page, so no link is ever assumed.
   */
  writeToHr?: PageLink | null
  className?: string
}

/** "mailto:" with the address escaped, so an odd address can't add a subject or a recipient. */
function mailtoHref(email: string): string {
  return `mailto:${encodeURIComponent(email).replace(/%40/g, '@')}`
}

function EmailText({ email }: { email: string }) {
  const at = email.indexOf('@')
  if (at === -1) return email
  return (
    <>
      {email.slice(0, at + 1)}
      <wbr />
      {email.slice(at + 1)}
    </>
  )
}

function ContactRow({
  name,
  detail,
  email,
  avatar,
}: {
  name: string
  detail: string
  email: string
  avatar: string | null
}) {
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 border-t border-border-subtle py-3 sm:grid-cols-[auto_minmax(0,1fr)_auto]">
      <Avatar aria-hidden="true" className="row-span-2 sm:row-span-1">
        <AvatarFallback>{avatar ?? <Users aria-hidden="true" className="size-4" />}</AvatarFallback>
      </Avatar>
      <span className="flex min-w-0 flex-col">
        <span className="text-body/[22px] font-semibold text-ink">{name}</span>
        {detail !== '' && <span className="text-small/[18px] text-ink-muted">{detail}</span>}
      </span>
      <a
        href={mailtoHref(email)}
        className={cn(APP_LINK, 'text-ui [overflow-wrap:anywhere] sm:whitespace-nowrap')}
      >
        {/* A break is allowed after the @ and nowhere else, so a narrow row splits the address into
            the name and the domain, not mid-word. Only a part too long for a row on its own breaks
            anywhere (overflow-wrap). The link's name is still the whole address. */}
        <EmailText email={email} />
      </a>
    </li>
  )
}

/**
 * Who to reach in HR: "HR contacts" and the line saying a person reads these, then one row per HR
 * person from the directory, then the shared HR inbox (a fixed entry, always last). Every escalation
 * panel and a not-found answer end with it. Rows stack below 640 px, with the email under the name.
 */
function HrContacts({
  contacts,
  variant = 'inline',
  writeToHr = null,
  className,
}: HrContactsProps) {
  const headingId = useId()
  return (
    <div
      data-slot="hr-contacts"
      className={cn(
        'flex flex-col gap-0.5',
        variant === 'card' && 'rounded-lg border border-border px-5 pt-3 pb-2',
        className,
      )}
    >
      <h3 id={headingId} className="m-0 text-small font-semibold text-ink">
        {conversationCopy.contactsHeading}
      </h3>
      <p className="m-0 mb-1 text-small text-ink-muted">{conversationCopy.contactsLine}</p>
      <ul aria-labelledby={headingId} className="m-0 list-none p-0">
        {contacts.map((contact, index) => (
          <ContactRow
            // Two people can share an address, so the place in the list is part of the key.
            key={`${index}:${contact.workEmail}`}
            name={contact.name}
            detail={[contact.jobTitle, contact.locationName].filter(Boolean).join(' · ')}
            email={contact.workEmail}
            // A name with no letters has no initials, and gets the icon like the shared inbox.
            avatar={initialsOf(contact.name) || null}
          />
        ))}
        <ContactRow
          name={HR_SHARED_INBOX.name}
          detail={HR_SHARED_INBOX.role}
          email={HR_SHARED_INBOX.workEmail}
          avatar={null}
        />
      </ul>
      {writeToHr && (
        <Link to={writeToHr.to} className={cn(APP_LINK, 'mt-3 self-start text-ui')}>
          {writeToHr.label}
        </Link>
      )}
    </div>
  )
}

export { HrContacts }
export type { HrContactsProps }
