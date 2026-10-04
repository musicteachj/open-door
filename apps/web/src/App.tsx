import { useGetHealth } from './api/generated'

export default function App() {
  const health = useGetHealth()

  // Only a 200 or a 503 carries a health report. Anything else, such as the empty 502 that Vite's
  // proxy sends when the API is down, or a problem-details error, means the check itself failed.
  let apiStatus = 'checking'
  if (health.isError) apiStatus = 'unreachable'
  else if (health.data) {
    const { status, data } = health.data
    apiStatus = status === 200 || status === 503 ? data.status : 'unreachable'
  }

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-3xl font-semibold">Open Door</h1>
      <p className="mt-2">Your open-door policy, now always open.</p>
      <output className="mt-6 block">API: {apiStatus}</output>
    </main>
  )
}
