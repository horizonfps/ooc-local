import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TAG_RE, TurnText } from './TurnText'

describe('TurnText', () => {
  it('renders plain narration in italics', () => {
    const { container } = render(<TurnText text="Ela abre a porta devagar." />)
    const em = container.querySelector('em')
    expect(em?.textContent).toBe('Ela abre a porta devagar.')
  })

  it('renders a speech line with bold name and no pipe on screen', () => {
    render(<TurnText text="**Yuna** | Você veio." />)
    const strong = screen.getByText('Yuna')
    expect(strong.tagName).toBe('STRONG')
    expect(screen.getByText('Você veio.')).toBeTruthy()
    expect(document.body.textContent).not.toContain('|')
  })

  it('only splits speech on the first pipe', () => {
    render(<TurnText text="**Yuna** | Vem — agora | rápido." />)
    expect(screen.getByText('Vem — agora | rápido.')).toBeTruthy()
  })

  it('falls back to narration when the speaker name is empty', () => {
    const { container } = render(<TurnText text="** ** | oi" />)
    expect(container.querySelector('strong')).toBeNull()
    expect(container.querySelector('em')?.textContent).toContain('oi')
  })

  it('removes an inline tag without leaving a double space before punctuation', () => {
    const { container } = render(<TurnText text="O sino toca. [STAT:reputacao:+1]" />)
    expect(container.querySelector('em')?.textContent).toBe('O sino toca.')
  })

  it('drops a line that becomes empty after tag removal', () => {
    const { container } = render(<TurnText text="[SPRITE:yuna:feliz]" />)
    expect(container.querySelector('.turnText-line')).toBeNull()
  })

  it('preserves prose brackets that are not tags', () => {
    const { container } = render(<TurnText text="Ele ri [risos] e sai." />)
    expect(container.querySelector('em')?.textContent).toBe('Ele ri [risos] e sai.')
  })

  it('retains an open bracket during streaming until it closes', () => {
    const { container, rerender } = render(<TurnText text="...e então [SPR" streaming />)
    expect(container.querySelector('em')?.textContent).toBe('...e então')

    rerender(<TurnText text="...e então [SPRITE:yuna:feliz] ela sorri" streaming />)
    expect(container.querySelector('em')?.textContent).toBe('...e então ela sorri')
  })

  it('shows the retained bracket raw once streaming stops', () => {
    const { container } = render(<TurnText text="...e então [SPR" streaming={false} />)
    expect(container.querySelector('em')?.textContent).toBe('...e então [SPR')
    expect(container.querySelector('.turnText-line--narration')?.getAttribute('title')).toBe(
      'Shown as the narrator wrote it',
    )
  })

  it('renders an incomplete speaker marker as narration and flips once it closes', () => {
    const { container, rerender } = render(<TurnText text="**Yu" streaming />)
    expect(container.querySelector('strong')).toBeNull()
    expect(container.querySelector('em')?.textContent).toBe('**Yu')

    rerender(<TurnText text="**Yuna** | oi" streaming />)
    expect(container.querySelector('strong')?.textContent).toBe('Yuna')
  })

  it('never interprets markdown headings or executes HTML', () => {
    const { container } = render(<TurnText text="# Título" />)
    expect(container.querySelector('em')?.textContent).toBe('# Título')
    expect(container.querySelector('script')).toBeNull()
  })

  it("renders nothing for an empty string, script tags included", () => {
    const { container } = render(<TurnText text="   " />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.firstChild).toBeNull()
  })

  it('mixes narration and two speech lines into three ordered blocks', () => {
    const { container } = render(
      <TurnText text={'Ela hesita.\n**Yuna** | Você veio.\n**Kaito** | Vim.'} />,
    )
    const lines = container.querySelectorAll('.turnText-line')
    expect(lines).toHaveLength(3)
    expect(lines[0].classList.contains('turnText-line--narration')).toBe(true)
    expect(lines[1].classList.contains('turnText-line--speech')).toBe(true)
    expect(lines[2].classList.contains('turnText-line--speech')).toBe(true)
  })

  it('cleans a paragraph carrying three different tag types', () => {
    const { container } = render(
      <TurnText text="O dia começa. [STAT:reputacao:+1][SPRITE:yuna:feliz][BG:praca]" />,
    )
    expect(container.querySelector('em')?.textContent).toBe('O dia começa.')
  })

  it('normalizes \\r\\n without leaving a phantom line', () => {
    const { container } = render(<TurnText text={'Linha um.\r\nLinha dois.'} />)
    expect(container.querySelectorAll('.turnText-line')).toHaveLength(2)
  })

  it('does not throw on unbalanced ** and an open bracket together, without streaming', () => {
    expect(() => render(<TurnText text="**Meio nome [ABERTO sem fim" />)).not.toThrow()
    expect(document.body.textContent).toContain('**Meio nome')
  })

  it('renders a 20000-character turn without throwing', () => {
    const long = 'Ela caminha pela vila. '.repeat(1000)
    expect(() => render(<TurnText text={long} />)).not.toThrow()
  })

  it('exports a TAG_RE mirroring the backend tag pattern', () => {
    expect(TAG_RE.source).toBe('\\[([A-Z][A-Z0-9_]*):([^\\[\\]\\n]*)\\]')
    expect('[STAT:reputacao:+1]'.replace(TAG_RE, '')).toBe('')
    expect('[risos]'.replace(TAG_RE, '')).toBe('[risos]')
  })

  it('preserves deliberate indentation in the rendered narration', () => {
    const { container } = render(<TurnText text="    Ele espera." />)
    expect(container.querySelector('em')?.textContent).toBe('    Ele espera.')
  })

  it('inserts a separator when a tag is glued between two words', () => {
    const { container } = render(<TurnText text="palavra[BG:sala]outra" />)
    expect(container.querySelector('em')?.textContent).toBe('palavra outra')
  })

  it('inserts a separator when a tag is glued between accented words', () => {
    const { container } = render(<TurnText text="olá[BG:sala]você" />)
    expect(container.querySelector('em')?.textContent).toBe('olá você')
  })

  it('renders a nested bracket raw without leaving an orphan closing bracket', () => {
    const { container } = render(<TurnText text="[BG:sala [interna]]" />)
    expect(container.querySelector('em')?.textContent).toBe('[BG:sala [interna]]')
  })

  it('does not drop the second tagged line because of the global regex lastIndex', () => {
    const { container } = render(
      <TurnText text={'Primeira [STAT:reputacao:+1] linha.\nSegunda [BG:sala] linha.'} />,
    )
    const lines = container.querySelectorAll('.turnText-line--narration')
    expect(lines).toHaveLength(2)
    expect(lines[0].textContent).toContain('Primeira')
    expect(lines[1].textContent).toContain('Segunda')
  })

  it('drops a HUD block and player echo, rendering only the remaining prose', () => {
    const { container } = render(
      <TurnText text={'# Turno 3\n**HUD**\nLocal: pátio\n\nVocê atravessa o pátio.'} />,
    )
    const lines = container.querySelectorAll('.turnText-line')
    expect(lines).toHaveLength(1)
    expect(container.querySelector('em')?.textContent).toBe('Você atravessa o pátio.')
  })

  it('drops the player echo line and renders only the other speaker', () => {
    const { container } = render(
      <TurnText text={'**Você** | vou até a Chloe\n**Chloe** | Oi.'} />,
    )
    const lines = container.querySelectorAll('.turnText-line')
    expect(lines).toHaveLength(1)
    expect(screen.getByText('Chloe').tagName).toBe('STRONG')
    expect(screen.getByText('Oi.')).toBeTruthy()
  })

  it('drops a HUD field line while streaming and keeps the open-bracket prose out of the block', () => {
    const { container } = render(<TurnText text={'Local: pátio\nEla ergue os olhos [SPR'} streaming />)
    const lines = container.querySelectorAll('.turnText-line')
    expect(lines).toHaveLength(1)
    expect(container.querySelector('em')?.textContent).toBe('Ela ergue os olhos')
  })

  it('renders a line matching a HUD field label but spoken by a character', () => {
    const { container } = render(<TurnText text="**Chloe** | Hora: de ir embora." />)
    expect(screen.getByText('Chloe').tagName).toBe('STRONG')
    expect(container.querySelector('.turnText-line--speech')?.textContent).toContain('Hora: de ir embora.')
  })

  it('renders nothing when the whole text is engine echo', () => {
    const { container } = render(<TurnText text={'# Turno 3\n**HUD**\nLocal: pátio'} />)
    expect(container.firstChild).toBeNull()
  })
})
