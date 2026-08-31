import './states.css'

export function Loading(props: { label: string; visuallyHidden?: boolean }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className={props.visuallyHidden ? 'visually-hidden' : undefined}>{props.label}</span>
    </div>
  )
}
