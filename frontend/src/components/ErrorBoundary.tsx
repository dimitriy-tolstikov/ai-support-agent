// демонстрирует: error boundary — перехват ошибок рендера с понятным UI
import { Component, type ReactNode } from "react";

interface State { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto mt-20 max-w-md rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <h2 className="mb-2 text-lg font-semibold text-red-700">Что-то пошло не так</h2>
          <p className="mb-4 text-sm text-red-600">{this.state.error.message}</p>
          <button
            className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white"
            onClick={() => this.setState({ error: null })}
          >
            Попробовать снова
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
