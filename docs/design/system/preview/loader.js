// Preview-only loader for Open Door component cards and UI kits.
// Fetches component .jsx files, strips import/export, transpiles with Babel standalone,
// and exposes every exported component on window.OpenDoor. Production code imports the
// components normally; this file exists so specimen pages render without a build step.
window.OD_FILES = [
  'components/core/Icon.jsx',
  'components/core/Button.jsx',
  'components/core/Logo.jsx',
  'components/navigation/Tooltip.jsx',
  'components/navigation/NavItem.jsx',
  'components/navigation/PersonaSwitcher.jsx',
  'components/navigation/PersonaMenu.jsx',
  'components/assistant/InlineError.jsx',
  'components/assistant/Composer.jsx',
  'components/assistant/TryAskingRow.jsx',
  'components/assistant/TryAskingList.jsx',
  'components/status/GlanceLink.jsx',
  'components/status/GlanceList.jsx',
  'components/status/SandboxIndicator.jsx',
  'components/landing/PersonaCard.jsx',
  'components/forms/SearchField.jsx',
  'components/forms/FilterSelect.jsx',
  'components/forms/FilterToggle.jsx',
  'components/directory/DirectoryRow.jsx',
  'components/directory/SkeletonRow.jsx',
  'components/directory/DirectoryTable.jsx',
  'components/directory/DetailRow.jsx',
  'components/directory/DetailList.jsx',
  'components/feedback/Toast.jsx',
  'components/feedback/Banner.jsx',
  'components/feedback/FullPageMessage.jsx'
];
window.loadOpenDoor = async function (root, files) {
  var mods = {};
  for (var i = 0; i < files.length; i++) {
    var res = await fetch(root + files[i]);
    var src = await res.text();
    var names = Array.from(src.matchAll(/export function (\w+)/g)).map(function (m) { return m[1]; });
    var code = src.replace(/^import[^\n]*\n/gm, '').replace(/export function /g, 'function ');
    var out = Babel.transform(code, { presets: ['react'] }).code;
    var keys = Object.keys(mods);
    var prelude = keys.length ? 'var {' + keys.join(',') + '} = OD;\n' : '';
    var fn = new Function('React', 'OD', prelude + out + '\nreturn {' + names.join(',') + '};');
    Object.assign(mods, fn(React, mods));
  }
  window.OpenDoor = mods;
  return mods;
};
