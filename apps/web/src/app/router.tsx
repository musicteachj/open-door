import { createBrowserRouter, type RouteObject } from 'react-router'
import { Root } from './Root'
import { RequireSession } from './RequireSession'
import { Ask, Directory, Landing, NotFound, Profile } from './placeholders'

// The component gallery is compiled in for development and for the e2e build, which sets
// VITE_GALLERY. In a production build both conditions are constants Vite folds to false, so the
// lazy import goes with them (scripts/check-no-gallery.mjs proves it). The route sits outside
// RequireSession: the gallery needs no sandbox.
const galleryRoutes: RouteObject[] =
  import.meta.env.DEV || import.meta.env.VITE_GALLERY === 'true'
    ? [
        {
          path: '/gallery',
          lazy: async () => ({ Component: (await import('./gallery/Gallery')).Gallery }),
        },
      ]
    : []

/** The route table. Tests build a memory router from it; the app builds a browser router. */
export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: '/', element: <Landing /> },
      ...galleryRoutes,
      {
        element: <RequireSession />,
        children: [
          { path: '/ask', element: <Ask /> },
          { path: '/directory', element: <Directory /> },
          { path: '/directory/:personId', element: <Profile /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
]

export const createAppRouter = () => createBrowserRouter(routes)
