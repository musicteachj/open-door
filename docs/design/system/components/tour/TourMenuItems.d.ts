/** The tour items for PersonaMenu's extra slot. Pass step while a tour is in progress. */
export declare function TourMenuItems(props: { step?: number; total?: number; onTake?: () => void; onResume?: () => void; onRestart?: () => void; state?: 'hover' | 'focus' }): JSX.Element;
/** "Start the tour?" Cancel is focused first. */
export declare function TourStartDialog(props: { id?: string; onStart?: () => void; onCancel?: () => void; cancelState?: 'focus' }): JSX.Element;
