SectionRow and SectionGroup build the handbook's table of contents. Put the column header (.od-sec-cols.od-sec-head) above the groups. Chapters use their number; addenda use the state code and a note like "For California employees".

~~~jsx
<div>
  <div className="od-sec-cols od-sec-head" aria-hidden="true"><span style={{ gridColumn: 'span 2' }}>Section</span><span>Applies to</span><span /><span>Last updated</span><span /></div>
  <SectionGroup num="4" title="Time off" id="ch-4">
    <SectionRow num="4.3" title="Sick leave" applies="Everyone" updated="Aug 3, 2026" href="/handbook/4.3" />
  </SectionGroup>
</div>
~~~

Pass appliesToYou only for restricted sections (a state, an employment type, or a location) that cover the person; for Priya that is CA-3.4 and CA-4.3. Rows are plain links in the Tab order.

The section page's chapter navigator uses the compact .od-sec-nav / .od-sec-nav__link classes with aria-current on the open section.
