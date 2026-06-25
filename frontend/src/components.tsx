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
  rowKey,
}: {
  columns: string[];
  rows: ReactNode[][];
  emptyTitle: string;
  emptyBody: string;
  rowKey?: (rowIndex: number) => Key;
}) {
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
            <tr key={rowKey?.(rowIndex) ?? rowIndex}>
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
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "success" | "warn" | "danger";
}) {
  return <span className={classNames("status-badge", `status-badge--${tone}`)}>{label}</span>;
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
  onClose,
  children,
}: {
  title: string;
  description?: string;
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
      <div className="modal-panel">
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
