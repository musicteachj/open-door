import { computeAccessibleName } from 'dom-accessibility-api'

/**
 * An element's accessible name. The package is a devDependency at the same version jest-dom uses,
 * so this computes names the same way `toHaveAccessibleName` does.
 */
export const accessibleNameOf = (element: Element): string => computeAccessibleName(element)
