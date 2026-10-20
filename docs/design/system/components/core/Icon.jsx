import React from 'react';

// Lucide icon geometry (lucide.dev, ISC license) for the glyphs Open Door uses.
// Production code uses lucide-react with the same names.
const PATHS = {
  'message-circle': [['path', { d: 'M7.9 20A9 9 0 1 0 4 16.1L2 22Z' }]],
  'calendar': [['rect', { width: 18, height: 18, x: 3, y: 4, rx: 2 }], ['path', { d: 'M16 2v4M8 2v4M3 10h18' }]],
  'users': [['path', { d: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2' }], ['circle', { cx: 9, cy: 7, r: 4 }], ['path', { d: 'M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75' }]],
  'book-open': [['path', { d: 'M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z' }], ['path', { d: 'M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z' }]],
  'code': [['path', { d: 'm16 18 6-6-6-6M8 6l-6 6 6 6' }]],
  'clock': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M12 6v6l4 2' }]],
  'info': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M12 16v-4M12 8h.01' }]],
  'circle-alert': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M12 8v4M12 16h.01' }]],
  'rotate-ccw': [['path', { d: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8' }], ['path', { d: 'M3 3v5h5' }]],
  'chevrons-up-down': [['path', { d: 'm7 15 5 5 5-5M7 9l5-5 5 5' }]],
  'chevron-right': [['path', { d: 'm9 18 6-6-6-6' }]],
  'arrow-right': [['path', { d: 'M5 12h14M12 5l7 7-7 7' }]],
  'arrow-up': [['path', { d: 'm5 12 7-7 7 7M12 19V5' }]],
  'map-pin': [['path', { d: 'M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0' }], ['circle', { cx: 12, cy: 10, r: 3 }]],
  'loader-circle': [['path', { d: 'M21 12a9 9 0 1 1-6.219-8.56' }]],
  'circle-play': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'm10 8 6 4-6 4z' }]],
  'search': [['circle', { cx: 11, cy: 11, r: 8 }], ['path', { d: 'm21 21-4.3-4.3' }]],
  'x': [['path', { d: 'M18 6 6 18M6 6l12 12' }]],
  'chevron-down': [['path', { d: 'm6 9 6 6 6-6' }]],
  'check': [['path', { d: 'M20 6 9 17l-5-5' }]],
  'lock': [['rect', { width: 18, height: 11, x: 3, y: 11, rx: 2, ry: 2 }], ['path', { d: 'M7 11V7a5 5 0 0 1 10 0v4' }]],
  'arrow-left': [['path', { d: 'm12 19-7-7 7-7M19 12H5' }]],
  'eye': [['path', { d: 'M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  'clipboard-check': [['rect', { width: 8, height: 4, x: 8, y: 2, rx: 1, ry: 1 }], ['path', { d: 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2' }], ['path', { d: 'm9 14 2 2 4-4' }]],
  'folder-lock': [['rect', { width: 8, height: 5, x: 14, y: 17, rx: 1 }], ['path', { d: 'M10 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v2.5' }], ['path', { d: 'M20 17v-2a2 2 0 1 0-4 0v2' }]],
  'layout-dashboard': [['rect', { width: 7, height: 9, x: 3, y: 3, rx: 1 }], ['rect', { width: 7, height: 5, x: 14, y: 3, rx: 1 }], ['rect', { width: 7, height: 9, x: 14, y: 12, rx: 1 }], ['rect', { width: 7, height: 5, x: 3, y: 16, rx: 1 }]],
  'log-out': [['path', { d: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' }], ['path', { d: 'm16 17 5-5-5-5M21 12H9' }]],
  'triangle-alert': [['path', { d: 'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3' }], ['path', { d: 'M12 9v4M12 17h.01' }]],
  'circle-check': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'm9 12 2 2 4-4' }]],
  'quote': [['path', { d: 'M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z' }], ['path', { d: 'M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z' }]],
  'minus': [['path', { d: 'M5 12h14' }]],
  'plus': [['path', { d: 'M5 12h14M12 5v14' }]],
  'chevron-left': [['path', { d: 'm15 18-6-6 6-6' }]],
  'chevron-up': [['path', { d: 'm18 15-6-6-6 6' }]],
  'circle-x': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'm15 9-6 6M9 9l6 6' }]],
  'calendar-minus': [['rect', { width: 18, height: 18, x: 3, y: 4, rx: 2 }], ['path', { d: 'M16 2v4M8 2v4M3 10h18M10 16h4' }]],
  'calendar-plus': [['rect', { width: 18, height: 18, x: 3, y: 4, rx: 2 }], ['path', { d: 'M16 2v4M8 2v4M3 10h18M12 14v4M10 16h4' }]],
  'calendar-x': [['rect', { width: 18, height: 18, x: 3, y: 4, rx: 2 }], ['path', { d: 'M16 2v4M8 2v4M3 10h18M10 14l4 4M14 14l-4 4' }]],
  'ban': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'm4.9 4.9 14.2 14.2' }]],
  'trash-2': [['path', { d: 'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' }], ['path', { d: 'M10 11v6M14 11v6' }]]
};

export function Icon({ name, size = 18, strokeWidth = 1.75, label, className, style }) {
  const parts = PATHS[name] || [];
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" className={className} style={Object.assign({ flex: 'none' }, style)}
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {parts.map((p, i) => React.createElement(p[0], Object.assign({ key: i }, p[1])))}
    </svg>
  );
}
