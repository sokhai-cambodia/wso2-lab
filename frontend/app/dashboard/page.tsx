'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://gateway.local.test'

type User = { sub: string; name: string; email: string | null }
type ApiResult = { status: number; ok: boolean; data: unknown } | { error: string } | null

const ENDPOINTS = [
  {
    id: 'public-resource',
    label: 'Public Resource',
    desc: 'No scope required. Returns gateway info.',
    color: 'green',
  },
  {
    id: 'secure-resource',
    label: 'Secure Resource',
    desc: 'APIM injects a signed JWT. Backend verifies and returns your claims.',
    color: 'blue',
  },
  {
    id: 'reports',
    label: 'Reports (Scope-Protected)',
    desc: 'Requires read:reports scope (analyst role). Returns 403 for other users.',
    color: 'purple',
  },
]

const colorMap: Record<string, string> = {
  green: 'bg-green-50 border-green-200 text-green-700',
  blue: 'bg-blue-50 border-blue-200 text-blue-700',
  purple: 'bg-purple-50 border-purple-200 text-purple-700',
}

export default function Dashboard() {
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)
  const [results, setResults] = useState<Record<string, ApiResult>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const session = sessionStorage.getItem('wso2_token')
    const storedUser = sessionStorage.getItem('wso2_user')
    if (!session || !storedUser) {
      router.replace('/')
      return
    }
    setUser(JSON.parse(storedUser))

    // /auth/me here is a liveness check only — it's routed through the secured
    // LabAPI, so its claims come from APIM's user-store lookup (empty for
    // federated GitHub users) rather than the id_token data captured at login.
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 8000)
    fetch(`${BACKEND}/auth/me`, {
      headers: { Authorization: `Bearer ${session}` },
      signal: controller.signal,
    })
      .then(res => {
        clearTimeout(timeoutId)
        if (!res.ok) { sessionStorage.clear(); router.replace('/') }
      })
      .catch(() => { clearTimeout(timeoutId); router.replace('/') })
    return () => { clearTimeout(timeoutId); controller.abort() }
  }, [router])

  async function callApi(endpoint: string) {
    const token = sessionStorage.getItem('wso2_token')
    if (!token) { router.replace('/'); return }
    setLoading(l => ({ ...l, [endpoint]: true }))
    setResults(r => ({ ...r, [endpoint]: null }))
    try {
      const res = await fetch(`${BACKEND}/lab/1.0/${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      setResults(r => ({ ...r, [endpoint]: { status: res.status, ok: res.ok, data } }))
    } catch (e) {
      setResults(r => ({ ...r, [endpoint]: { error: e instanceof Error ? e.message : String(e) } }))
    } finally {
      setLoading(l => ({ ...l, [endpoint]: false }))
    }
  }

  function handleLogout() {
    // Client-side only: the gateway strips Authorization on secured routes, so a
    // backend revoke call can never see the token. It expires at its natural TTL.
    sessionStorage.clear()
    router.replace('/')
  }

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-gray-300 border-t-gray-700 rounded-full" />
      </div>
    )
  }

  return (
    <main className="min-h-screen p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">WSO2 Lab Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            Logged in as <span className="font-medium text-gray-700">{user.name}</span>
            {user.email && <span className="text-gray-400"> · {user.email}</span>}
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-800 transition-colors"
        >
          Sign out
        </button>
      </div>

      {/* Session Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">IS Session</p>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span className="text-gray-500">Provider:</span> <span className="font-mono">WSO2 IS 7.0.0</span></div>
          <div><span className="text-gray-500">IdP:</span> <span className="font-mono">GitHub</span></div>
          <div><span className="text-gray-500">Name:</span> <span className="font-mono">{user.name}</span></div>
          <div><span className="text-gray-500">Email:</span> <span className="font-mono">{user.email ?? '—'}</span></div>
        </div>
      </div>

      {/* API Cards */}
      <div className="space-y-4">
        {ENDPOINTS.map(ep => {
          const result = results[ep.id]
          const busy = loading[ep.id]
          return (
            <div key={ep.id} className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full border ${colorMap[ep.color]} mb-2`}>
                    GET /lab/1.0/{ep.id}
                  </span>
                  <h2 className="font-semibold text-gray-900">{ep.label}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">{ep.desc}</p>
                </div>
                <button
                  onClick={() => callApi(ep.id)}
                  disabled={busy}
                  className="shrink-0 bg-gray-900 text-white text-sm px-4 py-2 rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
                >
                  {busy ? 'Testing…' : 'Test'}
                </button>
              </div>

              {result && (
                <div className="mt-4">
                  {'error' in result ? (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                      <span className="font-semibold">Error:</span> {result.error}
                    </div>
                  ) : (
                    <div className={`rounded-lg p-3 border text-sm ${result.ok ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`font-bold ${result.ok ? 'text-green-700' : 'text-red-700'}`}>
                          HTTP {result.status}
                        </span>
                        <span className={result.ok ? 'text-green-600' : 'text-red-600'}>
                          {result.ok ? '✓ Success' : '✗ Denied'}
                        </span>
                      </div>
                      <pre className="text-xs text-gray-700 overflow-auto whitespace-pre-wrap break-all">
                        {JSON.stringify(result.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="text-center text-xs text-gray-400 mt-8">
        IS tokens · APIM Gateway (gateway.local.test) · Backend internal-only
      </p>
    </main>
  )
}
