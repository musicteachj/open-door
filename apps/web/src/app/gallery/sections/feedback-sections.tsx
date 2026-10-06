import { useState } from 'react'
import { Banner } from '@/components/feedback/banner'
import { FullPageMessage } from '@/components/feedback/full-page-message'
import { InlineError } from '@/components/feedback/inline-error'
import { Button } from '@/components/ui/button'
import { Group, Section } from '../gallery-parts'

// The feedback components, each state under a heading with a stable id. The full-page messages
// pass `focusOnMount={false}`: on mount each would take focus, and the last one would steal it
// from the page's first Tab target. Each sits in a fixed-height frame, since the component fills
// whatever height its parent gives it.

const REQUEST_ID = '7f3a9c2e41b84d6a9e05c3b17d2f8a46'

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-96 w-full overflow-hidden rounded-md border border-border">{children}</div>
  )
}

function DismissibleBanner() {
  const [shown, setShown] = useState(true)
  return (
    <div className="flex w-full flex-col gap-3">
      {shown ? (
        <Banner
          message="This sandbox resets in 2 h 50 min. Everything you've done here will be cleared."
          onDismiss={() => setShown(false)}
        />
      ) : (
        <Button variant="secondary" size="sm" className="self-start" onClick={() => setShown(true)}>
          Show the banner again
        </Button>
      )}
    </div>
  )
}

export function FeedbackSections() {
  return (
    <>
      <Group title="Banner">
        <Section id="banner-default" title="Banner, default: press Dismiss to close it">
          <DismissibleBanner />
        </Section>
        <Section id="banner-no-dismiss" title="Banner, without a close button">
          <div className="w-full">
            <Banner message="This sandbox resets in 2 h 50 min. Everything you've done here will be cleared." />
          </div>
        </Section>
      </Group>
      <Group title="Inline error">
        <Section id="inline-error-retry" title="Inline error, with Retry">
          <div className="w-full max-w-xl">
            <InlineError message="Something went wrong sending that." onRetry={() => {}} />
          </div>
        </Section>
        <Section id="inline-error-message" title="Inline error, message only">
          <div className="w-full max-w-xl">
            <InlineError message="Something went wrong sending that." />
          </div>
        </Section>
      </Group>
      <Group title="Full-page message">
        <Section
          id="full-page-message-session-expired"
          title="Full-page message, outside the shell (session expired)"
        >
          <Frame>
            <FullPageMessage
              outsideShell
              focusOnMount={false}
              title="This sandbox has reset."
              body="Sandboxes last 24 hours. Start a new one to keep exploring."
            >
              <Button>Choose who to be</Button>
            </FullPageMessage>
          </Frame>
        </Section>
        <Section
          id="full-page-message-not-found"
          title="Full-page message, inside the shell (not found)"
        >
          <Frame>
            <FullPageMessage focusOnMount={false} title="We couldn't find that page.">
              <Button>Go to Ask</Button>
            </FullPageMessage>
          </Frame>
        </Section>
        <Section
          id="full-page-message-error"
          title="Full-page message, with a reference (something went wrong)"
        >
          <Frame>
            <FullPageMessage
              focusOnMount={false}
              title="Something went wrong on our side."
              body="Try again in a moment. If it keeps happening, this reference helps us find it:"
              reference={REQUEST_ID}
            >
              <Button>Retry</Button>
            </FullPageMessage>
          </Frame>
        </Section>
      </Group>
    </>
  )
}
