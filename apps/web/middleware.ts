import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PUBLIC_ROUTES = [
  '/',
  '/auth',
  '/status',
  '/_next/static',
  '/_next/image',
  '/favicon.ico',
]

const PUBLIC_PREFIXES = ['/legal/', '/api/v1/health']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (PUBLIC_ROUTES.includes(pathname)) {
    return NextResponse.next()
  }
  if (PUBLIC_PREFIXES.some(p => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  const sessionCookie = request.cookies.get('tm_session')
  const authHeader = request.headers.get('Authorization')

  const hasToken = !!sessionCookie || (!!authHeader && authHeader.startsWith('Bearer '))

  if (!hasToken) {
    const loginUrl = new URL('/auth', request.url)
    loginUrl.searchParams.set('redirect', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
}
