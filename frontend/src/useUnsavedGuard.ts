import { useEffect, useRef } from 'react'
import { t } from './i18n'

const BUILDER_TAB_RE = /^#\/builder\/([^/]+)\/([^/]+)\/?$/

export type UseUnsavedGuardOptions = {
  scenarioId: string
  onSave: () => Promise<void>
  onDiscard: () => void
}

function isSameScenarioTab(hash: string, scenarioId: string): boolean {
  const match = BUILDER_TAB_RE.exec(hash)
  return match !== null && match[1] === scenarioId
}

export function useUnsavedGuard(dirty: boolean, opts: UseUnsavedGuardOptions): void {
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty
  const optsRef = useRef(opts)
  optsRef.current = opts

  const lastHashRef = useRef(location.hash)
  const expectedHashRef = useRef<string | null>(null)
  const pendingHashRef = useRef<string | null>(null)
  const dialogRef = useRef<HTMLDialogElement | null>(null)

  useEffect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent) {
      if (!dirtyRef.current) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  useEffect(() => {
    const dialog = document.createElement('dialog')
    dialog.className = 'unsaved-guard-dialog'
    const titleId = `unsaved-guard-title-${Math.random().toString(36).slice(2)}`
    dialog.setAttribute('aria-labelledby', titleId)

    const heading = document.createElement('h2')
    heading.id = titleId
    heading.textContent = t('builder.editor.leave.title')

    const body = document.createElement('p')
    body.textContent = t('builder.editor.leave.body', { scenario: optsRef.current.scenarioId })

    const actions = document.createElement('div')
    actions.className = 'unsaved-guard-dialog-actions'

    const stayButton = document.createElement('button')
    stayButton.type = 'button'
    stayButton.textContent = t('builder.editor.leave.stay')

    const saveButton = document.createElement('button')
    saveButton.type = 'button'
    saveButton.textContent = t('builder.editor.leave.saveAndLeave')

    const discardButton = document.createElement('button')
    discardButton.type = 'button'
    discardButton.textContent = t('builder.editor.leave.discard')

    actions.append(stayButton, saveButton, discardButton)
    dialog.append(heading, body, actions)
    document.body.appendChild(dialog)
    dialogRef.current = dialog

    function goToPending() {
      const target = pendingHashRef.current
      pendingHashRef.current = null
      if (target === null) return
      expectedHashRef.current = target
      lastHashRef.current = target
      location.hash = target
    }

    function closeDialog() {
      if (dialog.open) dialog.close()
    }

    stayButton.addEventListener('click', () => {
      pendingHashRef.current = null
      closeDialog()
    })

    discardButton.addEventListener('click', () => {
      closeDialog()
      optsRef.current.onDiscard()
      goToPending()
    })

    saveButton.addEventListener('click', () => {
      closeDialog()
      optsRef.current.onSave().then(goToPending, () => {
        pendingHashRef.current = null
      })
    })

    return () => {
      document.body.removeChild(dialog)
      dialogRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    function handleHashChange() {
      const currentHash = location.hash

      if (expectedHashRef.current !== null) {
        const expected = expectedHashRef.current
        expectedHashRef.current = null
        if (currentHash === expected) {
          lastHashRef.current = currentHash
          return
        }
      }

      if (!dirtyRef.current || isSameScenarioTab(currentHash, optsRef.current.scenarioId)) {
        lastHashRef.current = currentHash
        return
      }

      const restoreTo = lastHashRef.current
      pendingHashRef.current = currentHash
      expectedHashRef.current = restoreTo
      location.replace(restoreTo)

      const dialog = dialogRef.current
      if (dialog) {
        dialog.showModal()
        const stayButton = dialog.querySelector('button')
        ;(stayButton as HTMLButtonElement | null)?.focus()
      }
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])
}
