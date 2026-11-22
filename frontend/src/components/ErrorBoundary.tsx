import { Component, type ReactNode } from 'react'
import { ErrorState } from './States'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <ErrorState message={`Something went wrong: ${this.state.error.message}`} onRetry={() => this.setState({ error: null })} />
        </div>
      )
    }
    return this.props.children
  }
}
