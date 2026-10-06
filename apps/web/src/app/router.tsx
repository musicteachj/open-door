import { createBrowserRouter, type RouteObject } from 'react-router'
import { Root } from './Root'
import { RequireSession } from './RequireSession'
import { NotFound } from '@/features/global-states/pages'
import { RootError, RouteError } from '@/features/global-states/route-error'
import { LandingPage } from '@/features/landing/landing-page'
import { AppShell } from '@/features/shell/app-shell'
import { HomePage } from '@/features/home/home-page'
import { DirectoryPage } from '@/features/directory/directory-page'
import { ProfilePage } from '@/features/directory/profile-page'

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
    errorElement: <RootError />,
    children: [
      { path: '/', element: <LandingPage /> },
      ...galleryRoutes,
      {
        element: <RequireSession />,
        children: [
          {
            // The shell sits under the session guard's reset key, so a switch remounts it. A
            // failed page below shows RouteError inside the shell's content sheet.
            element: <AppShell />,
            children: [
              {
                errorElement: <RouteError />,
                children: [
                  { path: '/ask', element: <HomePage /> },
                  { path: '/directory', element: <DirectoryPage /> },
                  { path: '/directory/:personId', element: <ProfilePage /> },
                  { path: '*', element: <NotFound /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
]

export const createAppRouter = () => createBrowserRouter(routes)
