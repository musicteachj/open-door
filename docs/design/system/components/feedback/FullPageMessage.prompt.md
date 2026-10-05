FullPageMessage fills the content sheet (or the whole window when there is no session) with a calm explanation and one way forward.

~~~jsx
<FullPageMessage title="This sandbox has reset." body="Sandboxes last 24 hours. Start a new one to keep exploring.">
  <Button iconRight="arrow-right" onClick={() => navigate('/')}>Choose who to be</Button>
</FullPageMessage>
<FullPageMessage title="We couldn't find that page."><a className="od-text-link" href="/">Go to Ask</a></FullPageMessage>
<FullPageMessage title="Something went wrong on our side." body="Try again in a moment. If it keeps happening, this reference helps us find it:" reference="7f3a9c2e">
  <Button icon="rotate-ccw" onClick={retry}>Retry</Button>
</FullPageMessage>
~~~

- Expired sessions render outside the shell. Not found and errors keep the shell with no nav item current.
