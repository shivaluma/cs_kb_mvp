import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type FeedbackContextValue = {
  error: string;
  notice: string;
  clearError: () => void;
  clearNotice: () => void;
  reportError: (message: string) => void;
  reportNotice: (message: string) => void;
};

const FeedbackContext = createContext<FeedbackContextValue | null>(null);

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const value = useMemo<FeedbackContextValue>(
    () => ({
      clearError: () => setError(""),
      clearNotice: () => setNotice(""),
      error,
      notice,
      reportError: (message) => {
        setError(message);
        setNotice("");
      },
      reportNotice: (message) => {
        setNotice(message);
        setError("");
      },
    }),
    [error, notice],
  );

  return <FeedbackContext.Provider value={value}>{children}</FeedbackContext.Provider>;
}

export function useFeedback() {
  const context = useContext(FeedbackContext);
  if (!context) {
    throw new Error("useFeedback must be used inside FeedbackProvider");
  }
  return context;
}
