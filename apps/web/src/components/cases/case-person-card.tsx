import { DetailRow } from '@/components/directory/detail-row'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { APP_LINK } from '@/components/assistant/link-class'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'
import { detailCopy } from './labels'

type CasePersonCardProps = {
  name: string
  title: string | null
  department: string | null
  location: string | null
  email: string | null
  className?: string
}

/**
 * Who sent the case: the directory card (name, title, department, location, work email) and the
 * line that Open Door sends no messages. HR replies by email or in person.
 */
function CasePersonCard({
  name,
  title,
  department,
  location,
  email,
  className,
}: CasePersonCardProps) {
  return (
    <div
      data-slot="case-person-card"
      className={cn('rounded-lg border border-border px-6 pt-5 pb-4 max-sm:px-4', className)}
    >
      <div className="flex items-center gap-3">
        <Avatar aria-hidden="true" size="lg">
          <AvatarFallback>{initialsOf(name)}</AvatarFallback>
        </Avatar>
        <div className="flex min-w-0 flex-col">
          <span className="text-body-lg/6 font-semibold">{name}</span>
          <span className="text-ui font-regular text-ink-muted">{title ?? '-'}</span>
        </div>
      </div>
      <dl className="m-0 mt-4">
        <DetailRow label={detailCopy.department} value={department ?? '-'} className="py-2.5" />
        <DetailRow label={detailCopy.location} value={location ?? '-'} className="py-2.5" />
        <DetailRow label={detailCopy.email} className="py-2.5">
          {email ? (
            <a href={`mailto:${email}`} className={APP_LINK}>
              {email}
            </a>
          ) : (
            '-'
          )}
        </DetailRow>
      </dl>
      <p className="m-0 mt-3 text-small text-ink-muted">{detailCopy.replyByEmail}</p>
    </div>
  )
}

export { CasePersonCard }
export type { CasePersonCardProps }
