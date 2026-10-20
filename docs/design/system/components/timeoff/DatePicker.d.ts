/** Month grid for one day or a range. Sunday first. Days off the person's schedule are shaded and muted but selectable (they're skipped, not counted). Company holidays carry a dot and show their name in a tooltip on hover and focus. Days before minKey are aria-disabled and struck through (PTO: today; sick time: 30 days back), and the legend says why. Today has a thin ring. First click starts a range (and is already a one-day selection); a later day ends it; the same day again keeps one day. Keyboard: arrows by day, Page Up and Down by month, Home and End to the week's ends, Enter or Space selects, Escape calls onDone. One tab stop (roving tabindex). Each day's accessible name carries its date and marks, e.g. "Thursday, November 26, Thanksgiving, company holiday". Maps to shadcn Calendar (react-day-picker) restyled. Also exports longDate(key). */
export interface DatePickerProps {
  id?: string;
  /** [year, monthIndex] shown. */
  month: [number, number];
  /** ISO dates, YYYY-MM-DD. */
  start?: string | null;
  end?: string | null;
  /** First day picked, waiting for the last; the hovered day previews the band. */
  inProgress?: boolean;
  hoverKey?: string | null;
  focusKey?: string | null;
  today: string;
  minKey?: string;
  holidays?: Record<string, string>;
  /** Legend line for disabled days. PTO: "Past days can't be picked for PTO"; sick time: "Sick time can go back 30 days, to September 20". */
  pastLabel?: string;
  /** Weekday numbers on the schedule, 0 = Sunday. */
  workdays?: number[];
  onSelect?: (key: string) => void;
  onMonthChange?: (month: [number, number]) => void;
  onFocusChange?: (key: string) => void;
  onHoverChange?: (key: string | null) => void;
  onDone?: () => void;
  /** Force a holiday tooltip open (specimens). */
  tipKey?: string;
  /** Render one day in a static state (specimens). */
  stateKey?: string;
  dayState?: 'hover' | 'focus' | 'active';
}
export declare function DatePicker(props: DatePickerProps): JSX.Element;
export declare function longDate(key: string): string;
/** "Fri, Oct 30": for the Dates field and the picker's hint line. */
export declare function shortDate(key: string): string;
export interface CalendarDayProps {
  dayKey: string;
  off?: boolean;
  holiday?: string;
  today?: boolean;
  selected?: boolean;
  disabled?: boolean;
  band?: 'start' | 'mid' | 'end';
  tabIndex?: number;
  tip?: boolean;
  state?: 'hover' | 'focus' | 'active';
  onSelect?: (key: string) => void;
  onHover?: (key: string) => void;
  onFocus?: (key: string) => void;
}
/** One day cell (gridcell plus button). Disabled days are struck through in disabled-fg on no fill, so they never read like future days. */
export declare function CalendarDay(props: CalendarDayProps): JSX.Element;
