# 04 · Directory and profile

**Phase:** 2 · **Viewport:** desktop · **Personas:** everyone; frames as Priya, Marcus, and Dana

Approved on 2026-10-04. The working frames are in
[`../../system/Directory.dc.html`](../../system/Directory.dc.html), and the components' source in
[`../../system/components/directory/`](../../system/components/directory/) and
[`../../system/components/forms/`](../../system/components/forms/). The screenshots here were
rendered from that file.

**Sample data:** the departments, the sort order, the first eight people, Marcus's team, and
Priya's and Leo's private details match the seed company. The other rows in the mockup are
illustrative, so the side-by-side comparison should focus on those.

## Purpose

Find anyone at Juniper Row and see how to reach them. A profile shows the work details everyone can
see and, for the person themselves and HR, their private details. Everyone else sees which private
fields exist and who can see them, but never the values.

## Layout

Inside the app shell, with "Directory" selected.

**List:** the page title "Directory" with the count ("120 people", or "44 of 120 people" while
searching or filtering) and the sandbox indicator on the right. Then a toolbar: the search field,
the Location and Department filters, "My team" for managers, and "Clear filters" while any filter
is on. Then the list: column labels (Name, Title, Department, Location), and one row per person
with initials, name, title, department, location, and a chevron. 50 rows, then "Showing 50 of 120"
and "Show more".

**Profile, a page of its own:** "← Directory" back to the list (keeping its place), the sandbox
indicator, then the header (initials, name with a "You" tag on your own profile, title,
department and location). Below, two panels side by side:

- **Work details:** title, department, location, manager (a link to their profile), and work
  email (a mail link).
- **Private details:** personal email, phone, home address, and date of birth.
  - **The person and HR** see the values, with "Only you and HR can see these." (or "Only Leo
    and HR…") and the note "Viewing private details is recorded in the audit log."
  - **Everyone else** sees each field as a locked row: a muted lock and "Visible to Leo and HR",
    never the value, and no warning color.

A profile is a page, not a panel beside the list, so it has a shareable URL, the manager link can
lead from profile to profile, each visit is one clear audit event, and the table keeps its width.

## Components used

App shell (Logo, Nav item, Persona switcher), Sandbox indicator, Search field, Filter select,
Filter toggle, Directory table, Directory row, Skeleton row, Detail list, Detail row (value and
locked), Button (secondary "Show more" and "Clear search", ghost "Clear filters").

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | Priya's view of the list, sorted by last name |
| Loading | `desktop-loading.png` | Eight skeleton rows, the toolbar and column labels kept, a short bar for the count; no shimmer |
| No results | `desktop-empty-search.png` | "No one matches "Jordn"." with "Clear search"; the count reads "0 of 120 people" |
| My team | `desktop-my-team.png` | Marcus with "My team" on: 44 people, tinted toggle, "Clear filters" |
| Locked profile | `desktop-profile-locked.png` | Priya viewing Leo Nakamura: private fields locked |
| HR view | `desktop-profile-hr.png` | Dana viewing Leo: values shown, with the audit note |
| Own profile | `desktop-profile-self.png` | Priya viewing herself: the "You" tag, her values, the audit note |
| Show more | `desktop-show-more.png` | The end of the first 50, with "Showing 50 of 120" and "Show more" |

## Interactions

- **Search** filters by name, title, or email as you type, with no search button. Its clear
  button (×) appears once there is text.
- **Filters:** Location and Department are single-choice menus with counts. "My team" is a toggle
  button (`aria-pressed`) shown only to managers, never disabled for everyone else. It means
  everyone who reports to them, directly or through a lead. "Clear filters" resets all of them.
- **With filters but no matches,** the empty state reads "No one matches these filters." with
  "Clear filters".
- **Each row is one link** to the profile. Its accessible name is the name, title, department,
  and location, plus "(you)" on your own row.
- **Show more** appends the next 50 using the API's cursor. There are no page numbers.
- **Profile:** "← Directory" returns to the list where you left it. The manager name opens their
  profile. The work email is a mail link.
- **Private details** are fetched only when the viewer may see them. A locked row is rendered
  from the field names alone, so a value is never sent to someone who can't see it. Every read
  is written to the audit log, the viewer's own included, and the note says so.
- **On a narrow screen** the rows stack under 760 px. That layout is written in the components
  but hasn't been designed or reviewed.

## Copy

- Title: "Directory"; count: "120 people", "44 of 120 people", "0 of 120 people"
- Search placeholder: "Search by name, title, or email"; clear button: "Clear search"
- Filters: "Location All", "Department All", "My team 44", "Clear filters"
- Empty: "No one matches "Jordn"." with "Clear search"; "No one matches these filters." with
  "Clear filters"
- List end: "Showing 50 of 120" and "Show more"
- Profile: "← Directory", "You", "Work details", "Private details", "Only you and HR can see
  these.", "Only Leo and HR can see these.", "Viewing private details is recorded in the audit
  log.", locked reason "Visible to Leo and HR"
- Field labels: Title, Department, Location, Manager, Work email, Personal email, Phone, Home
  address, Date of birth

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: rows stack, the toolbar wraps, and nothing overflows
- [ ] The list is sorted by last name, 50 at a time, and Show more appends the next page
- [ ] Search and both filters narrow the list and update the count; "Clear filters" resets them
- [ ] "My team" appears only for managers and shows everyone who reports to them, directly or
      indirectly
- [ ] Someone who isn't the person or HR never receives a private value: only locked rows
- [ ] Every read of private details writes an audit event, and the note shows whenever values
      are visible
- [ ] Every control and row is reachable by keyboard with a visible focus ring; axe reports no
      violations

## What the build needs from the API

Phase 1's directory API only pages through everyone, sorted by last name. This screen also needs:

- **search** by name, title, or work email
- **filters** by location, by department, and by "my team" (everyone under the signed-in manager)
- **counts** for the header ("44 of 120") and for each filter option

The seed's work emails also move from `opendoor.example` to `juniperrow.example`, as the profile
shows.
