import { NextResponse } from 'next/server'

// NextAuth removed — auth is handled by the FastAPI backend
export const GET = () => NextResponse.json({ error: 'Not used' }, { status: 404 })
export const POST = () => NextResponse.json({ error: 'Not used' }, { status: 404 })
