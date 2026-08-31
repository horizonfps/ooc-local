import { useRef, useState } from 'react'
import { t } from './i18n'

type Message = { role: 'user' | 'assistant'; content: string }

async function streamChat(message: string, onDelta: (delta: string) => void) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += value
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const event of events) {
      if (!event.startsWith('data: ')) continue
      const data = event.slice(6)
      if (data === '[DONE]') return
      const parsed = JSON.parse(data)
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.delta) onDelta(parsed.delta)
    }
  }
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const send = async () => {
    const message = input.trim()
    if (!message || busy) return
    setInput('')
    setBusy(true)
    setMessages((prev) => [...prev, { role: 'user', content: message }, { role: 'assistant', content: '' }])
    const appendDelta = (delta: string) =>
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = {
          role: 'assistant',
          content: next[next.length - 1].content + delta,
        }
        return next
      })
    try {
      await streamChat(message, (delta) => {
        appendDelta(delta)
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      })
    } catch (err) {
      appendDelta(`[${t('error')}: ${err instanceof Error ? err.message : String(err)}]`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="chat">
      <h1>{t('title')}</h1>
      <section className="messages">
        {messages.map((m, i) => (
          <p key={i} className={m.role}>
            {m.content}
          </p>
        ))}
        <div ref={bottomRef} />
      </section>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('placeholder')}
          autoFocus
        />
        <button type="submit" disabled={busy}>
          {t('send')}
        </button>
      </form>
    </main>
  )
}
