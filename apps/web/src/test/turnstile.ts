/** The token Cloudflare documents for its test keys. The setup file's fake check answers with it. */
export const DUMMY_TURNSTILE_TOKEN = 'XXXX.DUMMY.TOKEN.XXXX'

/**
 * What the fake `getTurnstileToken` (installed for every test by `setup.ts`, so none reaches
 * Cloudflare) saw. `containers` are the elements it was asked to render in, one per start. A test
 * sets `fail` to make the next starts get no token, as a widget error does, or `hold` (a promise it
 * resolves later) to keep the token pending.
 */
export const turnstileFake = {
  containers: [] as HTMLElement[],
  fail: false,
  hold: null as Promise<void> | null,
  reset() {
    this.containers = []
    this.fail = false
    this.hold = null
  },
}
