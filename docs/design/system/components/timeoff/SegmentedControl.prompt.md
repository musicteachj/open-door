SegmentedControl picks one of two short options, such as the request type.

~~~jsx
<SegmentedControl id="type" label="Type" value={type} onChange={setType}
  options={[{ value: 'pto', label: 'PTO' }, { value: 'sick', label: 'Sick time' }]} />
~~~

- Two or three options with one-word labels. Longer choices use ChoiceGroup.
- Disable it while the form submits.
