import type { AudioAlertResponse } from '../types/api';

interface AlertToastsProps {
  alerts: AudioAlertResponse[];
  onDismiss: (alertId: string) => void;
}

export function AlertToasts({ alerts, onDismiss }: AlertToastsProps): JSX.Element | null {
  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="alert-toast-stack" aria-live="polite" aria-label="Audio alerts">
      {alerts.map((alert) => (
        <article key={alert.id} className={`alert-toast is-${alert.severity}`}>
          <div className="alert-toast-copy">
            <span className="alert-toast-kicker">{alert.kind.toUpperCase()}</span>
            <strong>{alert.title}</strong>
            <p>
              {alert.channel_numbers.length > 0
                ? `CH ${alert.channel_numbers.join(', ')} · ${alert.message}`
                : alert.message}
            </p>
          </div>
          <button
            type="button"
            className="secondary icon-button"
            aria-label={`Dismiss ${alert.title}`}
            onClick={() => onDismiss(alert.id)}
          >
            ×
          </button>
        </article>
      ))}
    </div>
  );
}
