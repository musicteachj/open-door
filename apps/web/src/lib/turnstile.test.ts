import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The real module, not the setup file's fake.
vi.unmock('@/lib/turnstile')
const turnstileModule = await vi.importActual<typeof import('./turnstile')>('./turnstile')
const {
  getTurnstileToken,
  loadTurnstile,
  resetTurnstileForTests,
  SCRIPT_TIMEOUT_MS,
  TOKEN_TIMEOUT_MS,
  TURNSTILE_SCRIPT_URL,
} = turnstileModule

type Options = Parameters<NonNullable<Window['turnstile']>['render']>[1]

function installFakeApi() {
  const rendered: { id: string; container: HTMLElement; options: Options }[] = []
  const removed: string[] = []
  const executed: unknown[] = []
  let count = 0
  window.turnstile = {
    render: (container, options) => {
      count += 1
      const id = `w${count}`
      rendered.push({ id, container, options })
      return id
    },
    execute: (target) => {
      executed.push(target)
    },
    reset: () => {},
    remove: (id) => {
      removed.push(id!)
    },
  }
  return { rendered, removed, executed }
}

const scripts = () =>
  [...document.head.querySelectorAll<HTMLScriptElement>('script')].filter((s) =>
    s.src.startsWith('https://challenges.cloudflare.com'),
  )

/** Lets the pending promise attach the widget, then answers the script's load. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  resetTurnstileForTests()
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

afterEach(() => {
  delete window.turnstile
})

describe('loading the script', () => {
  it('does not load on import', () => {
    expect(scripts()).toHaveLength(0)
  })

  it("loads Cloudflare's exact URL once across starts", async () => {
    const fake = installFakeApi()
    const container = document.body.appendChild(document.createElement('div'))
    const first = getTurnstileToken(container)
    await settle()
    expect(scripts()).toHaveLength(1)
    expect(scripts()[0]!.src).toBe(
      'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
    )
    expect(TURNSTILE_SCRIPT_URL).toBe(scripts()[0]!.src)
    scripts()[0]!.dispatchEvent(new Event('load'))
    await settle()
    fake.rendered[0]!.options.callback('token-1')
    await expect(first).resolves.toBe('token-1')

    const second = getTurnstileToken(container)
    await settle()
    expect(scripts()).toHaveLength(1)
    fake.rendered[1]!.options.callback('token-2')
    await expect(second).resolves.toBe('token-2')
  })

  it('rejects when the script cannot load, and tries again on the next press', async () => {
    const container = document.body.appendChild(document.createElement('div'))
    const first = getTurnstileToken(container)
    const rejected = first.catch((error: Error) => error.message)
    scripts()[0]!.dispatchEvent(new Event('error'))
    expect(await rejected).toContain('could not be loaded')
    expect(scripts()).toHaveLength(0)

    const fake = installFakeApi()
    const second = getTurnstileToken(container)
    expect(scripts()).toHaveLength(1)
    scripts()[0]!.dispatchEvent(new Event('load'))
    await settle()
    fake.rendered[0]!.options.callback('late')
    await expect(second).resolves.toBe('late')
  })

  it('rejects when the script loads without its API', async () => {
    const loading = loadTurnstile()
    const rejected = loading.catch((error: Error) => error.message)
    scripts()[0]!.dispatchEvent(new Event('load'))
    expect(await rejected).toContain('without its API')
    expect(scripts()).toHaveLength(0)

    // A retry adds one script, not a second copy beside the first.
    const again = loadTurnstile()
    again.catch(() => {})
    expect(scripts()).toHaveLength(1)
  })

  describe('with a script that never answers', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    it('gives up after ten seconds, removes the script, and tries again on the next press', async () => {
      const container = document.body.appendChild(document.createElement('div'))
      const rejected = getTurnstileToken(container).catch((error: Error) => error.message)
      expect(scripts()).toHaveLength(1)
      await vi.advanceTimersByTimeAsync(SCRIPT_TIMEOUT_MS)
      expect(await rejected).toContain('too long')
      expect(scripts()).toHaveLength(0)

      const retry = getTurnstileToken(container)
      retry.catch(() => {})
      expect(scripts()).toHaveLength(1)
    })

    it('uses a script that finished after its timeout, without loading a second copy', async () => {
      const container = document.body.appendChild(document.createElement('div'))
      const rejected = getTurnstileToken(container).catch(() => 'rejected')
      await vi.advanceTimersByTimeAsync(SCRIPT_TIMEOUT_MS)
      expect(await rejected).toBe('rejected')
      // The removed script still ran, late, and defined the API.
      installFakeApi()
      await expect(loadTurnstile()).resolves.toBe(window.turnstile)
      expect(scripts()).toHaveLength(0)
    })

    it('does not time out once the script has loaded', async () => {
      installFakeApi()
      const loading = loadTurnstile()
      scripts()[0]!.dispatchEvent(new Event('load'))
      await expect(loading).resolves.toBeDefined()
      await vi.advanceTimersByTimeAsync(SCRIPT_TIMEOUT_MS * 2)
      expect(scripts()).toHaveLength(1)
    })
  })
})

describe('getting a token', () => {
  async function start() {
    const fake = installFakeApi()
    const container = document.body.appendChild(document.createElement('div'))
    const token = getTurnstileToken(container)
    scripts()[0]!.dispatchEvent(new Event('load'))
    await settle()
    return { ...fake, container, token }
  }

  it('renders one widget in the slot for this action, executes it, and removes it after', async () => {
    const { rendered, removed, executed, container, token } = await start()
    expect(rendered).toHaveLength(1)
    expect(rendered[0]!.container).toBe(container)
    expect(rendered[0]!.options).toMatchObject({
      action: 'start-sandbox',
      execution: 'execute',
      appearance: 'interaction-only',
    })
    expect(executed).toEqual(['w1'])
    expect(removed).toEqual([])
    rendered[0]!.options.callback('abc')
    await expect(token).resolves.toBe('abc')
    expect(removed).toEqual(['w1'])
  })

  it("uses the always-pass test key when the page has no site key, and the page's key when it has", async () => {
    const first = await start()
    expect(first.rendered[0]!.options.sitekey).toBe('1x00000000000000000000AA')
    first.rendered[0]!.options.callback('x')
    await first.token

    const meta = document.head.appendChild(document.createElement('meta'))
    meta.name = 'turnstile-site-key'
    meta.content = '0x4AAAAAAAreal'
    const container = document.body.appendChild(document.createElement('div'))
    const second = getTurnstileToken(container)
    await settle()
    expect(first.rendered[1]!.options.sitekey).toBe('0x4AAAAAAAreal')
    first.rendered[1]!.options.callback('y')
    await second
  })

  it.each([
    ['an error', (o: Options) => o['error-callback']('300030'), 'failed'],
    ['a timeout', (o: Options) => o['timeout-callback'](), 'timed out'],
    ['an expiry', (o: Options) => o['expired-callback'](), 'expired'],
  ])('rejects on %s, and still removes the widget', async (_name, fire, message) => {
    const { rendered, removed, token } = await start()
    const rejected = token.catch((error: Error) => error.message)
    fire(rendered[0]!.options)
    expect(await rejected).toContain(message)
    expect(removed).toEqual(['w1'])
  })

  it('settles once: a second answer from the same widget is ignored', async () => {
    const { rendered, removed, token } = await start()
    rendered[0]!.options.callback('first')
    rendered[0]!.options['error-callback']('late')
    await expect(token).resolves.toBe('first')
    expect(removed).toEqual(['w1'])
  })

  it('gives each start its own widget and token', async () => {
    const fake = await start()
    fake.rendered[0]!.options.callback('one')
    await fake.token
    const again = getTurnstileToken(fake.container)
    await settle()
    expect(fake.rendered).toHaveLength(2)
    expect(fake.rendered[1]!.id).not.toBe(fake.rendered[0]!.id)
    fake.rendered[1]!.options.callback('two')
    await expect(again).resolves.toBe('two')
  })

  it('rejects, and removes the widget, when a widget never calls back', async () => {
    vi.useFakeTimers()
    try {
      const fake = installFakeApi()
      const container = document.body.appendChild(document.createElement('div'))
      const token = getTurnstileToken(container)
      scripts()[0]!.dispatchEvent(new Event('load'))
      await vi.advanceTimersByTimeAsync(0)
      expect(fake.rendered).toHaveLength(1)
      const { removed } = fake
      const rejected = token.catch((error: Error) => error.message)
      await vi.advanceTimersByTimeAsync(TOKEN_TIMEOUT_MS)
      expect(await rejected).toContain('did not answer')
      expect(removed).toEqual(['w1'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('leaves room for a person to solve a checkbox before it gives up', () => {
    expect(TOKEN_TIMEOUT_MS).toBeGreaterThanOrEqual(60_000)
  })

  it('rejects when rendering throws', async () => {
    const fake = installFakeApi()
    window.turnstile!.render = vi.fn<() => string>(() => {
      throw new Error('no render')
    })
    const container = document.body.appendChild(document.createElement('div'))
    const token = getTurnstileToken(container)
    scripts()[0]!.dispatchEvent(new Event('load'))
    await expect(token).rejects.toThrow('no render')
    expect(fake.removed).toEqual([])
  })
})
