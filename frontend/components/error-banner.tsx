interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 rounded-lg border border-error-border bg-error-soft px-4 py-3 text-sm text-error-strong"
    >
      <span>{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-md border border-error-border-strong px-2.5 py-1 text-xs font-medium text-error-strong transition-colors hover:bg-error-muted"
        >
          重试
        </button>
      )}
    </div>
  );
}
