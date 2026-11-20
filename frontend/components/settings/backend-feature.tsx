import { BackendBadge } from "@/components/common";

export function BackendFeature({ title, description }: { title: string; description: string }) {
  return (
    <article className="settings-backend-feature card-surface">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <BackendBadge />
      <span title="Требует backend">
        <button type="button" className="button secondary small" disabled>
          Недоступно
        </button>
      </span>
    </article>
  );
}
