import { t } from '../i18n'
import type { CommandView } from '../api'
import './commandPalette.css'

// Grammar consumed by the backend's resolve_command; not translated.
export const SCENARIO_SIGIL = '!'
export const GLOBAL_SIGIL = '/'

export function paletteScope(query: string): CommandView['scope'] {
  return query[0] === SCENARIO_SIGIL ? 'scenario' : 'global'
}

export function filterCommands(commands: CommandView[], query: string): CommandView[] {
  const scope = paletteScope(query)
  const term = query.slice(1).toLowerCase()
  return commands.filter((c) => c.scope === scope && c.name.toLowerCase().startsWith(term))
}

export function CommandPalette(props: {
  commands: CommandView[]
  query: string
  activeIndex: number
  listboxId: string
  optionId: (index: number) => string
  onPick: (command: CommandView) => void
}) {
  const { commands, query, activeIndex, listboxId, optionId, onPick } = props
  const sigil = query[0]
  const scope = paletteScope(query)
  const scoped = commands.filter((c) => c.scope === scope)
  const filtered = filterCommands(commands, query)

  if (scoped.length === 0) {
    return (
      <div className="commandPalette">
        <p role="status">{t(scope === 'scenario' ? 'game.commands.emptyScenario' : 'game.commands.emptyGlobal')}</p>
      </div>
    )
  }

  if (filtered.length === 0) {
    return (
      <div className="commandPalette">
        <p role="status">{t('game.commands.noMatch')}</p>
      </div>
    )
  }

  return (
    <div className="commandPalette">
      <ul className="commandPalette__list" role="listbox" id={listboxId} aria-label={t('game.commands.palette.label')}>
        {filtered.map((command, i) => {
          const active = i === activeIndex
          return (
            <li
              key={command.name}
              id={optionId(i)}
              role="option"
              aria-selected={active}
              className={active ? 'commandPalette__option commandPalette__option--active' : 'commandPalette__option'}
              onMouseDown={(e) => {
                e.preventDefault()
                onPick(command)
              }}
              ref={active ? (el) => el?.scrollIntoView?.({ block: 'nearest' }) : undefined}
            >
              <strong>
                {sigil}
                {command.name}
              </strong>
              <span className="commandPalette__description">{command.description}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
