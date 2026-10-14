ApplicabilityBadge says who a handbook section applies to. Use the chip on section pages, search results, and the passage panel; use variant="text" in the section list's "Applies to" column.

~~~jsx
<ApplicabilityBadge />                                   // Applies to: Everyone
<ApplicabilityBadge state="CA" />                        // Applies to: California employees
<ApplicabilityBadge type="Hourly staff" state="CA" />    // Applies to: Hourly staff in California
<ApplicabilityBadge location="Denver HQ" variant="text" />
~~~
