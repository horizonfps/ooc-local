import { useEffect, useState } from 'react'

export type BuilderTab = 'identity' | 'world' | 'starts' | 'characters' | 'media'
const BUILDER_TABS: readonly BuilderTab[] = ['identity', 'world', 'starts', 'characters', 'media']

export type Route =
  | { name: 'sessions' }
  | { name: 'game'; id: string }
  | { name: 'builderList' }
  | { name: 'builderEditor'; id: string; tab: BuilderTab }

const BUILDER_EDITOR_RE = /^#\/builder\/([^/]+)\/([^/]+)\/?$/
const BUILDER_NO_TAB_RE = /^#\/builder\/([^/]+)\/?$/

function isBuilderTab(value: string): value is BuilderTab {
  return (BUILDER_TABS as readonly string[]).includes(value)
}

function needsBuilderTabReplace(hash: string): boolean {
  return BUILDER_NO_TAB_RE.test(hash) && !BUILDER_EDITOR_RE.test(hash)
}

function parseHash(hash: string): Route {
  const sessionMatch = /^#\/session\/([^/]+)$/.exec(hash)
  if (sessionMatch) return { name: 'game', id: sessionMatch[1] }

  const editorMatch = BUILDER_EDITOR_RE.exec(hash)
  if (editorMatch) {
    const tab = isBuilderTab(editorMatch[2]) ? editorMatch[2] : 'identity'
    return { name: 'builderEditor', id: editorMatch[1], tab }
  }

  const noTabMatch = BUILDER_NO_TAB_RE.exec(hash)
  if (noTabMatch) return { name: 'builderEditor', id: noTabMatch[1], tab: 'identity' }

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
      } else if (next.name === 'builderEditor' && needsBuilderTabReplace(hash)) {
        location.replace(`#/builder/${next.id}/identity`)
      }
    }
    apply()
    window.addEventListener('hashchange', apply)
    return () => window.removeEventListener('hashchange', apply)
  }, [])

  return route
}
