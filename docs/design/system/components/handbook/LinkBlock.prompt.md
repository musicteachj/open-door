LinkBlock sits under the section header, before the body.

~~~jsx
<LinkBlock title="State rules" note="California and Colorado add to this section." links={[
  { label: 'California addendum', meta: 'CA-4.3', href: '/handbook/CA-4.3', appliesToYou: true },
  { label: 'Colorado addendum', meta: 'CO-4.3', href: '/handbook/CO-4.3' }
]} />
<LinkBlock title="Supplements" links={[{ label: '§4.3 Sick leave', meta: 'Company handbook', href: '/handbook/4.3' }]} />
~~~
