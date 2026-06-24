import { NextResponse } from 'next/server'

// API test proxy removed — handled directly by the FastAPI backend (/api-test/{endpoint})
export const GET = () => NextResponse.json({ error: 'Not used' }, { status: 404 })
