import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStudio } from "../lib/store";
import type { LLMProvider } from "../types/api";

const PROVIDERS: LLMProvider[] = ["anthropic", "openai", "gemini", "litellm"];

export function Settings(): JSX.Element {
  const config = useStudio((s) => s.config);
  const setConfig = useStudio((s) => s.setConfig);
  const [keys, setKeys] = useState<Partial<Record<LLMProvider, string>>>({});
  const [licenseKey, setLicenseKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    setLicenseKey(config.license_key ?? "");
    setKeys({});
  }, [config]);

  const onSave = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const updated = await api.updateConfig({
        license_key: licenseKey || null,
        provider_keys: keys,
      });
      setConfig(updated);
      setSavedAt(new Date().toLocaleTimeString());
      setKeys({});
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Settings</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Provider keys and your Wisdom Layer license key. All values stay on this machine.
        </p>
      </header>

      <form onSubmit={onSave} className="max-w-xl space-y-5">
        <Field
          label="Wisdom Layer license key"
          rightSlot={
            config?.signup_url ? (
              <a
                href={config.signup_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs text-emerald-300 hover:text-emerald-200 hover:underline"
              >
                Don&apos;t have a key? Sign up →
              </a>
            ) : null
          }
          help="Optional. The Free tier works without one — a key unlocks higher caps."
        >
          <input
            type="password"
            autoComplete="new-password"
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="wl_free_… / wl_pro_… / wl_ent_…"
            className={inputClass}
          />
        </Field>

        <fieldset className="space-y-4">
          <legend className="text-sm text-zinc-300">Provider API keys</legend>
          {PROVIDERS.map((provider) => {
            const persisted = Boolean(config?.provider_keys[provider]);
            const fromEnv = config?.env_provider_keys?.includes(provider) ?? false;
            const configured = persisted || fromEnv;
            const help = persisted
              ? "Already configured. Enter a new value to replace it."
              : fromEnv
                ? "Configured via environment variable. Saving a value here overrides it."
                : undefined;
            return (
              <Field key={provider} label={provider} help={help}>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={keys[provider] ?? ""}
                  onChange={(e) => setKeys({ ...keys, [provider]: e.target.value })}
                  placeholder={configured ? "•••• replace" : `${provider} key`}
                  className={inputClass}
                />
              </Field>
            );
          })}
        </fieldset>

        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          {savedAt && <span className="text-xs text-zinc-500">Saved at {savedAt}</span>}
        </div>
      </form>
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none";

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
        <span className="block text-sm capitalize text-zinc-300">{props.label}</span>
        {props.rightSlot}
      </div>
      {props.children}
      {props.help && <p className="mt-1 text-xs text-zinc-500">{props.help}</p>}
    </div>
  );
}
