/**
 * Selectable card for one sandbox persona on the landing page: avatar initials, name, role, location, one line on what to try,
 * and a "Start as" cue. Selecting it starts a private sandbox. While one card is starting, it shows a spinner and
 * "Setting up Juniper Row…"; pass disabled to the others.
 * @startingPoint section="Landing" subtitle="Persona card for the sandbox picker" viewport="700x420"
 */
export interface PersonaCardProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onSelect'> {
  name: string;
  role: string;
  location: string;
  /** One sentence on what to try as this person. */
  prompt: string;
  /** Defaults to the first letters of the first two words of name. */
  initials?: string;
  /** starting shows the spinner and starting label, sets aria-busy, and blocks clicks. */
  status?: 'idle' | 'starting';
  /** Set on the other cards while one is starting. */
  disabled?: boolean;
  onSelect?: () => void;
  /** Defaults to "Start as {first name}". */
  startLabel?: string;
  startingLabel?: string;
  /** Specimens only: data-state="hover" | "focus". */
  'data-state'?: string;
}
export declare function PersonaCard(props: PersonaCardProps): JSX.Element;
