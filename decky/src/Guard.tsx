import { Component, type ReactNode } from "react";

// Keeps one part of a screen from taking the whole screen down: if what it wraps throws while drawing (a bad
// photo file, an unexpected value), that part shows nothing (or `fallback`) and the rest keeps working. The error
// goes to the console with `name`, for the Deck's debugger. A new `resetKey` (another player, another game) tries
// again.
export class Guard extends Component<{ name: string; resetKey?: string; fallback?: ReactNode; children: ReactNode },
  { failed: boolean; key?: string }> {
  state = { failed: false, key: this.props.resetKey };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { resetKey?: string }, state: { failed: boolean; key?: string }) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null;
  }

  componentDidCatch(error: unknown) {
    console.error(`map-helper: ${this.props.name} failed to draw`, error);
  }

  render() {
    return this.state.failed ? this.props.fallback ?? null : this.props.children;
  }
}
