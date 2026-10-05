import { createBrowserRouter, type RouteObject } from 'react-router'
import { Root } from './Root'
import { RequireSession } from './RequireSession'
import { Ask, Directory, Landing, NotFound, Profile } from './placeholders'

/** The route table. Tests build a memory router from it; the app builds a browser router. */
export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: '/', element: <Landing /> },
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
