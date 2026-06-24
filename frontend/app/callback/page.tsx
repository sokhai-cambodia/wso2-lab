'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export default function Callback() {
  const router = useRouter()
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state') ?? ''

    if (!code) {
      setError('No authorization code received from WSO2 IS.')
      return
    }

    fetch(`${BACKEND}/auth/exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
    })
      .then(res => {
        if (!res.ok) return res.json().then(d => Promise.reject(d.detail ?? 'Exchange failed'))
        return res.json()
      })
      .then(({ access_token }) => {
        sessionStorage.setItem('wso2_token', access_token)
        router.replace('/dashboard')
      })
      .catch(err => setError(String(err)))
  }, [router])

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
          <p className="text-red-600 font-semibold mb-2">Login failed</p>
          <p className="text-sm text-gray-500 mb-6">{error}</p>
          <a href="/" className="text-blue-600 hover:underline text-sm">Back to login</a>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="text-center text-gray-500">
        <div className="animate-spin w-8 h-8 border-4 border-gray-300 border-t-gray-700 rounded-full mx-auto mb-4" />
        <p>Completing login…</p>
      </div>
    </main>
  )
}
