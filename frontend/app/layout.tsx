import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'WSO2 Lab',
  description: 'WSO2 APIM + IS Lab Frontend',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen">{children}</body>
    </html>
  )
}
