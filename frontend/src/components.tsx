import { type Key, type ReactNode, useEffect, useId } from "react";

import { useAppContext } from "./app-context";
import { classNames } from "./utils";

export function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="splash-screen">
      <div className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function PageIntro({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-intro">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        <p className="lede">{description}</p>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  );
}

export function Card({
  title,
  description,
  children,
  className,
  headerActions,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
  headerActions?: ReactNode;
}) {
  return (
    <section className={classNames("card", className)}>
      {title ? (
        <header className={classNames("card-header", headerActions ? "card-header--with-actions" : null)}>
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          {headerActions}
        </header>
      ) : null}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function DataTable({
  columns,
  rows,
  emptyTitle,
  emptyBody,
  loading = false,
  loadingLabel = "Loading...",
  error = "",
  onRetry,
  rowKey,
  rowClassName,
  onRowClick,
}: {
  columns: string[];
  rows: ReactNode[][];
  emptyTitle: string;
  emptyBody: string;
  loading?: boolean;
  loadingLabel?: string;
  error?: string;
  onRetry?: () => void;
  rowKey?: (rowIndex: number) => Key;
  rowClassName?: (rowIndex: number) => string | false | null | undefined;
  onRowClick?: (rowIndex: number) => void;
}) {
  if (loading) {
    return (
      <div className="table-state" role="status" aria-live="polite">
        <div className="spinner spinner--small" aria-hidden="true" />
        <p>{loadingLabel}</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="table-state table-state--error" role="alert">
        <h3>Could not load data</h3>
        <p>{error}</p>
        {onRetry ? (
          <button className="secondary-button secondary-button--small" type="button" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
    );
  }
  if (!rows.length) return <EmptyState title={emptyTitle} body={emptyBody} />;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowKey?.(rowIndex) ?? rowIndex}
              className={classNames(rowClassName?.(rowIndex), onRowClick ? "data-table-row--interactive" : null)}
              role={onRowClick ? "button" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(rowIndex) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowClick(rowIndex);
                      }
                    }
                  : undefined
              }
            >
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

export function StatusBadge({
  ariaLabel,
  label,
  title,
  tone = "neutral",
}: {
  ariaLabel?: string;
  label: string;
  title?: string;
  tone?: "neutral" | "success" | "warn" | "danger";
}) {
  return (
    <span className={classNames("status-badge", `status-badge--${tone}`)} aria-label={ariaLabel} title={title}>
      {label}
    </span>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div>{children}</div>
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function Modal({
  title,
  description,
  panelClassName,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  panelClassName?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const titleId = useId();
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="modal-root" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button type="button" className="modal-backdrop" aria-label="Dismiss" onClick={onClose} />
      <div className={classNames("modal-panel", panelClassName)}>
        <div className="modal-panel-header">
          <h2 id={titleId}>{title}</h2>
        </div>
        <div className="modal-panel-body compact-form">
          {description ? <p className="modal-panel-desc">{description}</p> : null}
          {children}
        </div>
      </div>
    </div>
  );
}

export function ConfirmModal({
  title,
  description,
  confirmLabel,
  busyLabel = "Working...",
  cancelLabel = "Cancel",
  tone = "danger",
  busy = false,
  onClose,
  onConfirm,
  children,
}: {
  title: string;
  description?: string;
  confirmLabel: string;
  busyLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  children?: ReactNode;
}) {
  return (
    <Modal title={title} description={description} onClose={onClose}>
      {children}
      <div className="form-actions">
        <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          className={tone === "danger" ? "danger-button" : "primary-button"}
          type="button"
          onClick={() => void onConfirm()}
          disabled={busy}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export function ToastViewport() {
  const { toasts, dismissToast } = useAppContext();
  if (!toasts.length) return null;
  return (
    <div className="toast-viewport" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          type="button"
          className={classNames("toast", `toast--${toast.tone}`)}
          onClick={() => dismissToast(toast.id)}
        >
          <strong>{toast.title}</strong>
          {toast.description ? <span>{toast.description}</span> : null}
        </button>
      ))}
    </div>
  );
}
