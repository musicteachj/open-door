PersonaMenu is the switcher's menu: pick who to explore as, or sign out.

~~~jsx
<div className="od-persona-menu-anchor">
  {open && <PersonaMenu personas={PERSONAS} currentId="priya" onSelect={switchTo} onSignOut={endSession} />}
  <PersonaSwitcher name="Priya Raman" title="Visual Merchandiser" expanded={open} onClick={() => setOpen(!open)} />
</div>
~~~

- Choosing the current persona just closes the menu.
- Sign out ends the sandbox session; no confirmation.
