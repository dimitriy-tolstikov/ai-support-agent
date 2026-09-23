import { Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import ConversationList from "./pages/ConversationList";
import Chat from "./pages/Chat";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b bg-white px-6 py-3 shadow-sm">
        <h1 className="text-lg font-semibold">AI-оператор поддержки</h1>
      </header>
      <main className="mx-auto max-w-3xl p-4">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<ConversationList />} />
            <Route path="/c/:id" element={<Chat />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
