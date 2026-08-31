import type { ReactNode } from 'react'
import './states.css'

export function EmptyState(props: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="state state-empty">
      <p className="state-title">{props.title}</p>
      <p className="state-body">{props.body}</p>
      {props.action}
    </div>
  )
}
