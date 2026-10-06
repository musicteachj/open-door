// The directory's columns (directory.css, .od-dir-cols), shared by the column labels, a row, and a
// skeleton row so they line up: name, title, department, location, and a 16 px chevron. Below
// 760 px of viewport (the same number as the content width, which a media query can't read) a row stacks: the cells go under the name, indented past the avatar,
// and the chevron stays top right. The same rule is `.od-dir-row` in the design's CSS, which
// notes that the narrow layout is written but not yet designed or reviewed.
export const directoryColumns = [
  'grid grid-cols-[minmax(0,2.4fr)_minmax(0,1.8fr)_minmax(0,1.4fr)_minmax(0,1.2fr)_16px] items-center gap-x-6 px-3',
  'max-[760px]:grid-cols-[minmax(0,1fr)_16px] max-[760px]:h-auto max-[760px]:gap-y-0.5 max-[760px]:p-3',
].join(' ')
