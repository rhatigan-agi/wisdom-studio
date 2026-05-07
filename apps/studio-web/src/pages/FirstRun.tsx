import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useStudio } from "../lib/store";
import type { LLMProvider } from "../types/api";

const PROVIDERS: Array<{ value: LLMProvider; label: string; needsKey: boolean }> = [
  { value: "anthropic", label: "Anthropic (Claude)", needsKey: true },
  { value: "openai", label: "OpenAI (GPT)", needsKey: true },
  { value: "gemini", label: "Google Gemini", needsKey: true },
  { value: "ollama", label: "Ollama (local)", needsKey: false },
  { value: "litellm", label: "LiteLLM (multi-provider proxy)", needsKey: true },
];

export function FirstRun(): JSX.Element {
  const navigate = useNavigate();
  const setConfig = useStudio((s) => s.setConfig);
  const lockedLlm = useStudio((s) => s.config?.locked_llm ?? null);
  const signupUrl = useStudio((s) => s.config?.signup_url ?? null);
  const [provider, setProvider] = useState<LLMProvider>(lockedLlm?.provider ?? "anthropic");
  const [apiKey, setApiKey] = useState("");
  const [licenseKey, setLicenseKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsKey = PROVIDERS.find((p) => p.value === provider)?.needsKey ?? true;

  const onSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const updated = await api.updateConfig({
        license_key: licenseKey || null,
        provider_keys: needsKey ? { [provider]: apiKey } : {},
      });
      setConfig(updated);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-zinc-950 px-6 py-10">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-lg space-y-6 rounded-xl border border-zinc-800 bg-zinc-900/40 p-8"
      >
        <header>
          <h1 className="text-xl font-semibold text-zinc-100">Welcome to Wisdom Studio</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Set your LLM provider and (optionally) a Wisdom Layer license key. Both stay on
            this machine — Studio never sends them anywhere except the provider's own API.
          </p>
        </header>

        <Field
          label="LLM provider"
          help={lockedLlm ? "This deployment locks the LLM provider." : undefined}
        >
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as LLMProvider)}
            disabled={lockedLlm !== null}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none disabled:opacity-60"
          >
            {lockedLlm ? (
              <option value={lockedLlm.provider}>
                {PROVIDERS.find((p) => p.value === lockedLlm.provider)?.label ??
                  lockedLlm.provider}
              </option>
            ) : (
              PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))
            )}
          </select>
        </Field>

        {provider === "ollama" && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Ollama also embeds memories with a local model. Pull it once before your first chat:
            <pre className="mt-1 overflow-x-auto rounded bg-zinc-950 px-2 py-1 font-mono text-amber-100">ollama pull nomic-embed-text</pre>
          </div>
        )}

        {needsKey && (
          <Field label={`${provider.charAt(0).toUpperCase()}${provider.slice(1)} API key`}>
            <input
              type="password"
              autoComplete="new-password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              required
              className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none"
            />
          </Field>
        )}

        <Field
          label="Wisdom Layer license key (optional)"
          help="Free tier works without one. A wl_pro_… or wl_ent_… key unlocks directives, dreams, and the critic."
          rightSlot={
            signupUrl ? (
              <a
                href={signupUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs text-emerald-300 hover:text-emerald-200 hover:underline"
              >
                Don&apos;t have a key? Sign up →
              </a>
            ) : null
          }
        >
          <input
            type="password"
            autoComplete="new-password"
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="wl_free_… / wl_pro_… / wl_ent_…"
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none"
          />
        </Field>

        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Continue"}
        </button>
      </form>
    </div>
  );
}

function Field(props: {
  label: string;
  help?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
}): JSX.Element {
  // Wrapper is a <div>, not a <label>: a <label> forwards stray clicks to its
  // first nested form control, which can fire unrelated buttons inside a
  // multi-control field. See note in NewAgent.tsx for the original bug.
  return (
    <div className="block">
      <div className="mb-1 flex items-center justify-between gap-3">
        <span className="block text-sm text-zinc-300">{props.label}</span>
        {props.rightSlot}
      </div>
      {props.children}
      {props.help && <p className="mt-1 text-xs text-zinc-500">{props.help}</p>}
    </div>
  );
}
