import { Lock } from 'lucide-react'
import { Link } from 'react-router'
import { DetailList } from '@/components/directory/detail-list'
import { DetailRow } from '@/components/directory/detail-row'
import { DirectoryRow } from '@/components/directory/directory-row'
import { DirectoryTable, type DirectoryItem } from '@/components/directory/directory-table'
import { SkeletonRow } from '@/components/directory/skeleton-row'
import { Group, Section } from '../gallery-parts'

// The directory's table, row, skeleton row, and the profile's detail list and rows. Hover and
// focus are not shown: the tests hover and focus the real elements. The links lead to the
// directory, since a gallery state has no person to open.

const PEOPLE: DirectoryItem[] = [
  {
    id: 'dana',
    name: 'Dana Whitfield',
    title: 'HR Business Partner',
    department: 'People',
    location: 'Denver HQ',
    to: '/directory',
  },
  {
    id: 'priya',
    name: 'Priya Raman',
    title: 'Visual Merchandiser',
    department: 'Store Operations',
    location: 'Oakland store',
    to: '/directory',
  },
  {
    id: 'leo',
    name: 'Leo Nakamura',
    title: 'Sales Associate',
    department: 'Store Operations',
    location: 'Oakland store',
    to: '/directory',
  },
]

const LEO = PEOPLE[2]!

export function DirectorySections() {
  return (
    <Group title="Directory table, row, and skeleton row">
      <Section id="directory-table-default" title="Directory table, with your own row (Priya)">
        <div className="w-full">
          <DirectoryTable items={PEOPLE} youId="priya" />
        </div>
      </Section>
      <Section id="directory-table-loading" title="Directory table, loading (eight skeleton rows)">
        <div className="w-full">
          <DirectoryTable items={[]} loading />
        </div>
      </Section>
      <Section id="directory-row-default" title="Directory row, default">
        <div className="w-full">
          <DirectoryRow {...LEO} />
        </div>
      </Section>
      <Section id="directory-row-you" title="Directory row, your own">
        <div className="w-full">
          <DirectoryRow {...LEO} isYou />
        </div>
      </Section>
      <Section id="skeleton-row-default" title="Skeleton row">
        <div className="w-full">
          <SkeletonRow />
        </div>
      </Section>
      <Section id="detail-list-values" title="Detail lists, values, a link, and the audit note">
        <div className="w-full max-w-content">
          <DetailList title="Work details">
            <DetailRow label="Title" value="Sales Associate" />
            <DetailRow label="Manager">
              <Link to="/directory">Marcus Bell</Link>
            </DetailRow>
            <DetailRow label="Work email" value="leo.nakamura@juniperrow.example" />
          </DetailList>
          <DetailList
            title="Private details"
            note="Only you and HR can see these."
            auditNote="Viewing private details is recorded in the audit log."
            className="mt-6"
          >
            <DetailRow label="Phone" value="(510) 555-0175" />
          </DetailList>
        </div>
      </Section>
      <Section id="detail-list-locked" title="Detail list, locked (a lock and the reason)">
        <div className="w-full max-w-content">
          <DetailList title="Private details" icon={Lock}>
            <DetailRow label="Personal email" locked reason="Visible to Leo and HR" />
            <DetailRow label="Phone" locked reason="Visible to Leo and HR" />
            <DetailRow label="Home address" locked reason="Visible to Leo and HR" />
            <DetailRow label="Date of birth" locked reason="Visible to Leo and HR" />
          </DetailList>
        </div>
      </Section>
    </Group>
  )
}
