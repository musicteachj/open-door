import { Lock } from 'lucide-react'
import type { MouseEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { useGetPerson, useGetPersonPrivate, type DirectoryCard } from '@/api/generated'
import { useMe } from '@/app/useMe'
import { PageHeader } from '@/components/core/page-header'
import { DetailList } from '@/components/directory/detail-list'
import { DetailRow } from '@/components/directory/detail-row'
import { InlineError } from '@/components/feedback/inline-error'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import { isNotFound } from '@/features/global-states/errors'
import { NotFound } from '@/features/global-states/pages'
import { initialsOf } from '@/lib/initials'
import { isUuid } from '@/lib/uuid'
import { originOf, oneStepFurther, type DirectoryOrigin } from './directory-origin'

// A person's profile at /directory/:personId, from docs/design/screens/04-directory. The shell
// supplies the sandbox indicator and the page's one <main>.
//
// Who sees the private values is decided here from the server's /me alone: the viewer is that
// person, or HR. Everyone else gets locked rows built from the field names, and the values are
// never requested. The server enforces the same rule (and audits each read); this keeps the
// browser from asking at all.

// The generated client puts the ID into the URL as it is, so anything that isn't a UUID (a path,
// a query string, "../me") must never reach it.

export function ProfilePage() {
  const { personId = '' } = useParams()
  if (!isUuid(personId)) return <NotFound />
  return <Profile personId={personId} />
}

function Profile({ personId }: { personId: string }) {
  const { data: me } = useMe()
  // Not found is shown here, inside the shell. Any other failure goes to the route's boundary.
  const person = useGetPerson(personId, { query: { throwOnError: (error) => !isNotFound(error) } })
  const location = useLocation()
  const navigate = useNavigate()
  const origin = originOf(location.state)

  if (isNotFound(person.error)) return <NotFound />

  // Back reuses the history entry the list is in, so its search, filters, and scroll all return.
  // A profile opened directly has no list behind it, so it opens the plain directory.
  const goBack = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!origin || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    void navigate(-origin.steps)
  }

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <PageHeader
        back={{
          to: `/directory${origin?.directorySearch ?? ''}`,
          label: 'Directory',
          onClick: goBack,
        }}
        right={<PageSandboxIndicator />}
      />
      <LoadingStatus loading={!(person.data && me)} text="Loading the profile" />
      {person.data && me ? (
        <ProfileBody
          person={person.data}
          viewerId={me.id}
          viewerIsHr={me.isHrAdmin}
          origin={origin}
        />
      ) : (
        <ProfileSkeleton />
      )}
    </div>
  )
}

function ProfileBody({
  person,
  viewerId,
  viewerIsHr,
  origin,
}: {
  person: DirectoryCard
  viewerId: string
  viewerIsHr: boolean
  origin: DirectoryOrigin | null
}) {
  const isYou = person.id === viewerId
  const name = `${person.givenName} ${person.familyName}`
  const manager = person.manager
  return (
    <>
      <div className="mt-8 flex items-center gap-5">
        <Avatar aria-hidden="true" className="size-16">
          <AvatarFallback className="text-h2">{initialsOf(name)}</AvatarFallback>
        </Avatar>
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-x-2.5">
            <h1 className="text-h1 wrap-break-word text-ink">{name}</h1>
            {isYou && (
              <span className="inline-flex h-5 flex-none items-center rounded-xs border border-border-strong px-1.5 text-caption text-ink-muted">
                You
              </span>
            )}
          </div>
          <span className="text-body">{person.title}</span>
          <span className="text-ui font-regular text-ink-muted">
            {person.department.name} · {person.location.name}
          </span>
        </div>
      </div>

      <div className="mt-10 grid grid-cols-[repeat(auto-fit,minmax(min(100%,360px),1fr))] items-start gap-8">
        <DetailList title="Work details">
          <DetailRow label="Title" value={person.title} />
          <DetailRow label="Department" value={person.department.name} />
          <DetailRow label="Location" value={person.location.name} />
          <DetailRow label="Manager">
            {manager ? (
              <Link
                to={`/directory/${encodeURIComponent(manager.id)}`}
                state={oneStepFurther(origin)}
              >
                {manager.givenName} {manager.familyName}
              </Link>
            ) : (
              <span className="text-ink-muted">None listed</span>
            )}
          </DetailRow>
          <DetailRow label="Work email">
            <a href={`mailto:${person.workEmail}`}>{person.workEmail}</a>
          </DetailRow>
        </DetailList>

        {isYou || viewerIsHr ? (
          <PrivateSection personId={person.id} givenName={person.givenName} isYou={isYou} />
        ) : (
          <LockedSection givenName={person.givenName} />
        )}
      </div>
    </>
  )
}

const PRIVATE_FIELDS = ['Personal email', 'Phone', 'Home address', 'Date of birth'] as const

/** Everyone else: each field by name, with who can see it. No request, so no value to leak. */
function LockedSection({ givenName }: { givenName: string }) {
  return (
    <DetailList title="Private details" icon={Lock}>
      {PRIVATE_FIELDS.map((label) => (
        <DetailRow key={label} label={label} locked reason={`Visible to ${givenName} and HR`} />
      ))}
    </DetailList>
  )
}

/** Mounted only for the person and for HR, so the request exists only for them. */
function PrivateSection({
  personId,
  givenName,
  isYou,
}: {
  personId: string
  givenName: string
  isYou: boolean
}) {
  const details = useGetPersonPrivate(personId)
  // The status stays mounted through every state, so it announces a change, not its arrival.
  return (
    <>
      <LoadingStatus loading={details.isPending} text="Loading the private details" />
      {details.isPending ? (
        <DetailList title="Private details" icon={Lock}>
          <PrivateSkeletonRows />
        </DetailList>
      ) : details.isError ? (
        <section aria-labelledby="private-heading">
          <div className="mb-3 flex items-center gap-2">
            <Lock aria-hidden="true" className="size-4 text-ink-muted" />
            <h2 id="private-heading" className="text-body font-semibold">
              Private details
            </h2>
          </div>
          <InlineError
            className="mt-0"
            message="We couldn't load the private details."
            onRetry={() => void details.refetch()}
          />
        </section>
      ) : (
        <DetailList
          title="Private details"
          icon={Lock}
          note={
            isYou ? 'Only you and HR can see these.' : `Only ${givenName} and HR can see these.`
          }
          auditNote="Viewing private details is recorded in the audit log."
        >
          <DetailRow label="Personal email" value={details.data.personalEmail} />
          <DetailRow label="Phone" value={details.data.phone} />
          <DetailRow label="Home address" value={details.data.homeAddress} />
          <DetailRow label="Date of birth" value={formatDate(details.data.dateOfBirth)} />
        </DetailList>
      )}
    </>
  )
}

/** "2000-06-22" as "June 22, 2000". A calendar date, so no timezone moves it. */
function formatDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return isoDate
  return date.toLocaleDateString('en-US', { dateStyle: 'long', timeZone: 'UTC' })
}

function PrivateSkeletonRows() {
  return PRIVATE_FIELDS.map((label) => (
    <DetailRow key={label} label={label}>
      <Skeleton className="inline-block h-3 w-40" />
    </DetailRow>
  ))
}

/** While the person loads: the header's shape, so the page doesn't jump. */
function ProfileSkeleton() {
  return (
    <div aria-busy="true" className="mt-8 flex items-center gap-5">
      <Skeleton className="size-16 rounded-full" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-40" />
      </div>
    </div>
  )
}
