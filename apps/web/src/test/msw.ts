import { setupServer } from 'msw/node'

// One server for the whole test run. Each test adds its own handlers with `server.use(...)`;
// `setup.ts` resets them after every test and fails any request nobody handled.
export const server = setupServer()
