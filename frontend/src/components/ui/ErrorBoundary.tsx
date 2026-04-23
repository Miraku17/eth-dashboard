import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; label?: string };
type State = { error: Error | null };

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }): void {
    // Surface in console so you can debug; the card UI below shows a friendly msg.
    // eslint-disable-next-line no-console
    console.error(`Panel "${this.props.label ?? "unknown"}" crashed:`, error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-down/30 bg-down/5 p-5">
          <p className="text-sm font-semibold text-down">
            {this.props.label ? `${this.props.label}: ` : ""}something went wrong
          </p>
          <p className="text-xs text-slate-400 mt-1 font-mono break-words">
            {this.state.error.message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 text-xs text-slate-300 hover:text-white underline"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
