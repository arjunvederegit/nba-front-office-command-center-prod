"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

interface Toast {
  id: number;
  kind: "success" | "error" | "info";
  message: string;
}

const ToastContext = createContext<(kind: Toast["kind"], message: string) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++counter.current;
    setToasts((current) => [...current, { id, kind, message }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4200);
  }, []);

  const styles: Record<Toast["kind"], string> = {
    success: "border-pass/50 bg-pass/15 text-pass",
    error: "border-fail/50 bg-fail/15 text-fail",
    info: "border-accent/50 bg-accent/15 text-accent",
  };

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-lg backdrop-blur ${styles[toast.kind]}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
