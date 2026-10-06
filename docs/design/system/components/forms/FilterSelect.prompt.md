FilterSelect narrows a list by one field, such as location or department.

~~~jsx
<FilterSelect label="Location" allLabel="All locations" value={loc} onChange={setLoc}
  options={[{ value: 'Denver HQ', label: 'Denver HQ', count: 40 }, { value: 'Oakland store', label: 'Oakland store', count: 45 }, { value: 'Austin warehouse', label: 'Austin warehouse', count: 35 }]} />
~~~

- Active state is shown by the value text and the tint fill, never color alone.
- Show a ghost "Clear filters" button beside the filters while any are active.
