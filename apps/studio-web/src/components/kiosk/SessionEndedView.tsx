import { Hourglass, Sparkles } from "lucide-react";
import { useStudio } from "../../lib/store";
import type { SessionStateName } from "../../types/api";

// Rendered in place of the chat surface when the backend has gated this
// session (`session_ended` for TTL expiry, `token_cap_reached` for token
// budget). Both end-states are deliberately final — there is no retry button
// because the only path forward is a fresh container (try-it-now demo) or
// for the operator to lift the cap. The optional CTA points wherever the
// fork wants visitors to convert (signup, marketing page, calendar).
//
// `WISDOM_STUDIO_SESSION_END_CTA_HREF=` (empty) suppresses the CTA entirely
// — same convention as `WISDOM_STUDIO_SIGNUP_URL`.
export function SessionEndedView(props: { state: SessionStateName }): JSX.Element {
  const ctaHref = useStudio((s) => s.config?.session_end_cta_href ?? null);
  const ctaLabel = useStudio((s) => s.config?.session_end_cta_label ?? null);
  const isCap = props.state === "token_cap_reached";

  const Icon = isCap ? Sparkles : Hourglass;
  const title = isCap ? "Session limit reached" : "Session ended";
  const body = isCap
    ? "You've used the messages this preview includes. Spin up your own to keep going."
    : "Thanks for trying it out. Your session window has ended.";

  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-300">
        <Icon className="h-5 w-5" />
      </div>
      <div className="max-w-md space-y-2">
        <h2 className="text-lg font-semibold text-zinc-100">{title}</h2>
        <p className="text-sm text-zinc-400">{body}</p>
      </div>
      {ctaHref && (
        <a
          href={ctaHref}
          target="_blank"
          rel="noreferrer"
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500"
        >
          {ctaLabel ?? "Get started"}
        </a>
      )}
    </div>
  );
}
