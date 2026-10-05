export interface MenuPersona { id: string; name: string; title: string; initials?: string; }

/** Menu that opens above PersonaSwitcher: the four sandbox personas (current one tinted and checked), a note that switching starts a new conversation, a separator, and Sign out. Arrow keys move between items; Escape is handled by the anchor. Maps to shadcn DropdownMenu with a RadioGroup. Place inside .od-persona-menu-anchor. */
export interface PersonaMenuProps {
  personas: MenuPersona[];
  currentId: string;
  onSelect?: (persona: MenuPersona) => void;
  /** Ends the sandbox session and returns to the landing page. */
  onSignOut?: () => void;
  signOutHref?: string;
  label?: string;
  note?: string;
  className?: string;
}
export declare function PersonaMenu(props: PersonaMenuProps): JSX.Element;
