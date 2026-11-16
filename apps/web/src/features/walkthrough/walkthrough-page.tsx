import { ArrowLeft } from 'lucide-react'
import { useEffect, useId } from 'react'
import { Link, useLocation } from 'react-router'
import { Logo } from '@/components/core/logo'
import { PublicFooter } from '@/components/landing/public-footer'
import { backTarget } from '@/lib/walkthrough-back'
import { metadataLine, POSTER_SRC, VIDEO_SRC, WALKTHROUGH } from './recording'
import { Transcript } from './transcript'

// Screen 16 (docs/design/screens/16-walkthrough): the guided tour, recorded once with the live
// assistant, and its transcript. Public, like the landing: no session, no persona, no app
// navigation (ADR 0019). A signed-in visitor sees it too; nothing here redirects.

const HEADING = 'The recorded walkthrough'
const INTRO =
  'The guided tour, recorded with the live assistant: the same ten steps you can take yourself.'
const NO_VIDEO = 'Your browser can’t play this video. The transcript below has every step.'

export function WalkthroughPage() {
  const location = useLocation()
  const headingId = useId()
  // Steps can be linked (`/walkthrough#step-3`), but the page arrives after the browser has looked
  // for the step, so it is brought into view here once the transcript is in the page.
  const { hash } = location
  useEffect(() => {
    if (/^#step-\d+$/.test(hash)) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash])
  return (
    <div className="flex min-h-dvh flex-col bg-surface px-5 text-ink sm:px-6">
      <div className="mx-auto w-full max-w-292 flex-1">
        <header className="flex h-18 items-center justify-between gap-4">
          <Link
            to="/"
            aria-label="Open Door home"
            className="rounded-sm focus-visible:outline-offset-4"
          >
            <Logo />
          </Link>
          <Link
            to={backTarget(location.state)}
            className="-mr-2.5 inline-flex h-9 items-center gap-2 rounded-sm px-2.5 text-ui font-semibold text-ink no-underline hover:bg-neutral-hover"
          >
            <ArrowLeft aria-hidden="true" className="size-4 shrink-0" />
            Back to the demo
          </Link>
        </header>

        <main className="pt-14">
          <div className="flex max-w-190 flex-col gap-3">
            <h1 id={headingId} className="m-0 text-h1">
              {HEADING}
            </h1>
            <p className="m-0 text-body-lg text-pretty text-ink-muted">{INTRO}</p>
          </div>

          <figure className="m-0 mt-10">
            {/* The frame is the video's own border, with no clipping wrapper, so its focus ring shows.
                The browser's own controls; never autoplays; downloads nothing until played
                (screen 16's build decisions). Captions are for sound, and the file has none: the
                transcript below is the video's text alternative (WCAG 1.2.1, video only). */}
            {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
            <video
              controls
              preload="none"
              poster={POSTER_SRC}
              width={1440}
              height={900}
              aria-labelledby={headingId}
              className="block aspect-[16/10] w-full rounded-lg border border-border bg-surface-raised"
            >
              <source src={VIDEO_SRC} type="video/mp4" />
              {NO_VIDEO}
            </video>
            <figcaption className="mt-3 text-small text-ink-muted tabular-nums">
              {metadataLine(WALKTHROUGH)}
            </figcaption>
          </figure>

          <Transcript steps={WALKTHROUGH.steps} className="mt-20" />
        </main>
      </div>
      <PublicFooter />
    </div>
  )
}
