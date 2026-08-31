import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { Loading } from './Loading'

describe('EmptyState', () => {
  it('renders the optional action when given', () => {
    render(<EmptyState title="No sessions" body="Start one" action={<button>Start</button>} />)
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('renders nothing extra when no action is given', () => {
    render(<EmptyState title="No sessions" body="Start one" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('Loading', () => {
  it('has role status and aria-live polite', () => {
    render(<Loading label="Loading…" />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('Loading…')
  })

  it('keeps the text in the DOM but visually hidden when visuallyHidden is set', () => {
    render(<Loading label="Loading…" visuallyHidden />)
    const text = screen.getByText('Loading…')
    expect(text).toHaveClass('visually-hidden')
  })
})

describe('ErrorState', () => {
  it('shows the cause in a details element', () => {
    render(<ErrorState title="Broke" body="Try again" cause="stack trace" />)
    expect(screen.getByText('stack trace')).toBeInTheDocument()
    expect(screen.getByText('stack trace').closest('details')).toBeInTheDocument()
  })

  it('renders no details when there is no cause', () => {
    const { container } = render(<ErrorState title="Broke" body="Try again" />)
    expect(container.querySelector('details')).toBeNull()
  })

  it('only renders the retry button when onRetry is given, and calls it on click', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const { rerender } = render(<ErrorState title="Broke" body="Try again" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()

    rerender(<ErrorState title="Broke" body="Try again" onRetry={onRetry} />)
    await user.click(screen.getByRole('button'))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
