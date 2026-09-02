import { Fragment } from 'react'
import { t } from '../i18n'
import { GLOBAL_SIGIL, SCENARIO_SIGIL } from './CommandPalette'
import type { CommandView } from '../api'
import './playGuide.css'

export function PlayGuide(props: { playGuide: string | null; commands: CommandView[] }) {
  const { playGuide, commands } = props
  if (playGuide === null && commands.length === 0) return null

  return (
    <details className="playGuide" open>
      <summary>{t('game.guide.label')}</summary>
      <div className="playGuide__body">
        {playGuide !== null ? <p className="playGuide__prose">{playGuide}</p> : null}
        {commands.length > 0 ? (
          <div className="playGuide__commands">
            <p className="playGuide__commandsLabel">{t('game.commands.listLabel')}</p>
            <dl className="playGuide__list">
              {commands.map((command) => (
                <Fragment key={`${command.scope}-${command.name}`}>
                  <dt>{(command.scope === 'global' ? GLOBAL_SIGIL : SCENARIO_SIGIL) + command.name}</dt>
                  <dd>{command.description}</dd>
                </Fragment>
              ))}
            </dl>
            <p className="playGuide__hint">{t('game.commands.hint')}</p>
          </div>
        ) : null}
      </div>
    </details>
  )
}
