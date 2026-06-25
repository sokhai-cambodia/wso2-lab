'use client'
import { useState } from 'react'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export default function Home() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin() {
    setLoading(true)
    setError('')
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 8000)
    try {
      const res = await fetch(`${BACKEND}/auth/login-url`, { signal: controller.signal })
      clearTimeout(timeoutId)
      if (!res.ok) throw new Error(`Backend error: ${res.status}`)
      const { url } = await res.json()
      window.location.href = url
    } catch (e) {
      clearTimeout(timeoutId)
      setError(
        e instanceof DOMException && e.name === 'AbortError'
          ? 'Request timed out — is the backend running? (docker compose ps)'
          : e instanceof Error ? e.message : String(e)
      )
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="bg-white rounded-2xl shadow-lg p-10 w-full max-w-md text-center">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">WSO2 Lab</h1>
          <p className="mt-2 text-gray-500 text-sm">
            APIM 4.3.0 · Identity Server 7.0.0
          </p>
        </div>

        <div className="bg-blue-50 rounded-lg p-4 mb-8 text-left text-sm text-blue-800">
          <p className="font-semibold mb-1">What this demo shows:</p>
          <ul className="list-disc list-inside space-y-1">
            <li>GitHub login via WSO2 IS (OIDC)</li>
            <li>Public API — no extra auth</li>
            <li>Secure API — JWT assertion from APIM</li>
            <li>Reports API — scope-protected (analyst role)</li>
          </ul>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full bg-gray-900 text-white py-3 px-6 rounded-xl font-medium hover:bg-gray-700 disabled:opacity-50 transition-colors"
        >
          {loading ? 'Redirecting…' : 'Login with GitHub via WSO2 IS'}
        </button>

        <p className="mt-6 text-xs text-gray-400">
          GitHub → WSO2 IS → APIM Gateway → FastAPI Backend
        </p>
      </div>
    </main>
  )
}
