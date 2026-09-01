import { useEffect, useState } from 'react'

export type Route = { name: 'sessions' } | { name: 'game'; id: string } | { name: 'builderList' }

function parseHash(hash: string): Route {
  const match = /^#\/session\/([^/]+)$/.exec(hash)
  if (match) return { name: 'game', id: match[1] }
  if (/^#\/builder\/?$/.test(hash)) return { name: 'builderList' }
  return { name: 'sessions' }
}

export function navigate(hash: string): void {
  location.hash = hash.startsWith('#/') ? hash : '#/'
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(location.hash))

  useEffect(() => {
    function apply() {
      const hash = location.hash
      const next = parseHash(hash)
      setRoute(next)
      if (next.name === 'sessions' && hash !== '' && hash !== '#/') {
        location.replace('#/')
      }
    }
    apply()
    window.addEventListener('hashchange', apply)
    return () => window.removeEventListener('hashchange', apply)
  }, [])

  return route
}
