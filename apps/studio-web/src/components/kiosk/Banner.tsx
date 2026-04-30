import { useStudio } from "../../lib/store";

// The server (`apps/studio-api/studio_api/settings.py`) sanitizes
// `WISDOM_STUDIO_BANNER_HTML` with `bleach.clean` before exposing it via
// `GET /api/config`, stripping any tag or attribute outside a small inline
// allowlist (a, strong, em, b, i, br, span). That makes it safe to feed
// directly to `dangerouslySetInnerHTML` here — Studio never trusts the raw
// env var, only the cleaned output.
export function Banner(): JSX.Element | null {
  const html = useStudio((s) => s.config?.banner_html ?? null);
  if (!html) return null;
  return (
    <div
      role="status"
      className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-xs text-amber-200"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
