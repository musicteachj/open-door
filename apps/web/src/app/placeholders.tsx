import { useParams } from 'react-router'

// Stage 6 replaces the directory pages. Until then these are
// plain markup that proves the routing and the session guard. The shell supplies the page's one
// <main>, so none of these renders its own.

export function Directory() {
  return (
    <div className="p-8 text-ink">
      <h1>Directory</h1>
    </div>
  )
}

export function Profile() {
  const { personId } = useParams()
  return (
    <div className="p-8 text-ink">
      <h1>Profile</h1>
      <p>{personId}</p>
    </div>
  )
}
