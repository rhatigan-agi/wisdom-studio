import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, X } from "lucide-react";
import { api } from "../lib/api";
import { useStudio } from "../lib/store";
import type {
  AgentCreate,
  Archetype,
  ExampleSummary,
  LLMProvider,
  StorageKind,
} from "../types/api";

const ARCHETYPES: Array<{ value: Archetype; label: string; hint: string }> = [
  { value: "balanced", label: "Balanced", hint: "general-purpose default" },
  { value: "research", label: "Research", hint: "synthesis across sources" },
  { value: "coding_assistant", label: "Coding assistant", hint: "code review, refactor" },
  { value: "consumer_support", label: "Consumer support", hint: "policy + identity verification" },
  { value: "strategic_advisors", label: "Strategic advisor", hint: "long-horizon reasoning" },
  { value: "lightweight_local", label: "Lightweight local", hint: "small models, low resource" },
];

const PROVIDERS: LLMProvider[] = ["anthropic", "openai", "gemini", "ollama", "litellm"];

export function NewAgent(): JSX.Element {
  const navigate = useNavigate();
  const config = useStudio((s) => s.config);
  const setAgents = useStudio((s) => s.setAgents);

  const lockedLlm = config?.locked_llm ?? null;

  const [draft, setDraft] = useState<AgentCreate>({
    name: "",
    role: "",
    archetype: "balanced",
    persona: "",
    directives: [],
    llm_provider: lockedLlm?.provider ?? "anthropic",
    llm_model: lockedLlm?.model ?? undefined,
    storage_kind: "sqlite",
    conversation_starters: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  const [loadingTemplate, setLoadingTemplate] = useState<string | null>(null);
  const [activeTemplate, setActiveTemplate] = useState<{ slug: string; name: string } | null>(
    null,
  );
  const [starterDraft, setStarterDraft] = useState("");
  const formRef = useRef<HTMLFormElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listExamples();
        if (!cancelled) setExamples(list);
      } catch (err) {
        console.error("studio: load examples failed", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const configuredProviders: LLMProvider[] = PROVIDERS.filter((p) => {
    if (p === "ollama") return true;
    return Boolean(config?.provider_keys[p]);
  });

  const onPickTemplate = async (slug: string, name: string): Promise<void> => {
    setError(null);
    setLoadingTemplate(slug);
    try {
      const payload = await api.getExample(slug);
      // Locked-LLM deployments override the template's provider/model so the
      // form reflects what will actually be created.
      const provider = lockedLlm?.provider ?? payload.llm_provider;
      const model = lockedLlm?.model ?? payload.llm_model ?? undefined;
      setDraft({
        name: payload.name,
        role: payload.role ?? "",
        archetype: payload.archetype,
        persona: payload.persona ?? "",
        directives: payload.directives ?? [],
        llm_provider: provider,
        llm_model: model,
        llm_tier: payload.llm_tier ?? null,
        storage_kind: payload.storage_kind ?? "sqlite",
        storage_url: payload.storage_url ?? undefined,
        conversation_starters: payload.conversation_starters ?? [],
      });
      setActiveTemplate({ slug, name });
      formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingTemplate(null);
    }
  };

  const clearTemplate = (): void => {
    setActiveTemplate(null);
    setDraft({
      name: "",
      role: "",
      archetype: "balanced",
      persona: "",
      directives: [],
      llm_provider: lockedLlm?.provider ?? "anthropic",
      llm_model: lockedLlm?.model ?? undefined,
      storage_kind: "sqlite",
      conversation_starters: [],
    });
  };

  const addStarter = (): void => {
    const trimmed = starterDraft.trim();
    if (!trimmed) return;
    if (trimmed.length > 80) {
      setError("Conversation starters must be 80 characters or fewer.");
      return;
    }
    const existing = draft.conversation_starters ?? [];
    if (existing.length >= 5) {
      setError("Maximum of 5 conversation starters.");
      return;
    }
    setError(null);
    setDraft({ ...draft, conversation_starters: [...existing, trimmed] });
    setStarterDraft("");
  };

  const removeStarter = (index: number): void => {
    const existing = draft.conversation_starters ?? [];
    setDraft({
      ...draft,
      conversation_starters: existing.filter((_, i) => i !== index),
    });
  };

  const onSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    if (!draft.name.trim()) {
      setError("Agent name is required.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await api.createAgent(draft);
      const agents = await api.listAgents();
      setAgents(agents);
      navigate(`/agents/${created.agent_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-100">New agent</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Each archetype maps to an SDK <code>AdminDefaults</code> factory.
        </p>
      </header>

      {examples.length > 0 && (
        <section className="mb-8 max-w-2xl">
          <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wider text-zinc-500">
            <Sparkles className="h-3.5 w-3.5" />
            Start from a template
          </div>
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {examples.map((ex) => {
              const isActive = activeTemplate?.slug === ex.slug;
              return (
                <li key={ex.slug}>
                  <button
                    type="button"
                    onClick={() => onPickTemplate(ex.slug, ex.name)}
                    disabled={loadingTemplate !== null}
                    className={`w-full rounded-md border px-3 py-2 text-left transition disabled:opacity-50 ${
                      isActive
                        ? "border-emerald-600 bg-emerald-900/20"
                        : "border-zinc-800 bg-zinc-900/40 hover:border-emerald-700/50 hover:bg-zinc-900"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-zinc-100">{ex.name}</span>
                      <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400">
                        {ex.archetype}
                      </span>
                    </div>
                    {ex.persona_preview && (
                      <p className="mt-1 truncate text-xs text-zinc-500">{ex.persona_preview}</p>
                    )}
                    <p className="mt-1 text-[11px] text-zinc-600">
                      {ex.directive_count} {ex.directive_count === 1 ? "directive" : "directives"}
                      {loadingTemplate === ex.slug && " · loading…"}
                      {isActive && " · prefilled below"}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-zinc-500">
            Clicking a template prefills the form below. Edit anything you want, then press
            Create.
          </p>
        </section>
      )}

      <form ref={formRef} onSubmit={onSubmit} className="max-w-2xl space-y-5">
        {activeTemplate && (
          <div className="flex items-center justify-between rounded-md border border-emerald-700/40 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-200">
            <span>
              Prefilled from template{" "}
              <span className="font-mono text-emerald-100">{activeTemplate.name}</span>
            </span>
            <button
              type="button"
              onClick={clearTemplate}
              className="rounded px-2 py-0.5 text-emerald-300 hover:bg-emerald-900/30 hover:text-emerald-100"
            >
              Reset
            </button>
          </div>
        )}
        <Field label="Name" required>
          <input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Writer"
            required
            className={inputClass}
          />
        </Field>

        <Field label="Role" help="One-line description used in the system prompt.">
          <input
            value={draft.role ?? ""}
            onChange={(e) => setDraft({ ...draft, role: e.target.value })}
            placeholder="long-form writing assistant"
            className={inputClass}
          />
        </Field>

        <Field label="Archetype">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {ARCHETYPES.map((a) => (
              <label
                key={a.value}
                className={`flex cursor-pointer flex-col rounded-md border px-3 py-2 transition ${
                  draft.archetype === a.value
                    ? "border-emerald-600 bg-emerald-900/20"
                    : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-600"
                }`}
              >
                <input
                  type="radio"
                  name="archetype"
                  value={a.value}
                  checked={draft.archetype === a.value}
                  onChange={() => setDraft({ ...draft, archetype: a.value })}
                  className="hidden"
                />
                <span className="text-sm font-medium text-zinc-100">{a.label}</span>
                <span className="text-xs text-zinc-500">{a.hint}</span>
              </label>
            ))}
          </div>
        </Field>

        <Field label="Persona" help="Free-form system-prompt extension.">
          <textarea
            value={draft.persona ?? ""}
            onChange={(e) => setDraft({ ...draft, persona: e.target.value })}
            rows={4}
            className={`${inputClass} font-mono`}
          />
        </Field>

        <Field
          label="Conversation starters"
          help="Optional clickable chips shown on an empty chat. Up to 5, 80 chars each."
        >
          <div className="space-y-2">
            {(draft.conversation_starters ?? []).length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {(draft.conversation_starters ?? []).map((starter, idx) => (
                  <li
                    key={`${idx}-${starter}`}
                    className="flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-900/60 py-1 pl-3 pr-1 text-xs text-zinc-200"
                  >
                    <span>{starter}</span>
                    <button
                      type="button"
                      onClick={() => removeStarter(idx)}
                      aria-label={`Remove starter: ${starter}`}
                      className="rounded-full p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <input
                value={starterDraft}
                onChange={(e) => setStarterDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addStarter();
                  }
                }}
                maxLength={80}
                placeholder="What would you like to ask first?"
                disabled={(draft.conversation_starters ?? []).length >= 5}
                className={`${inputClass} disabled:opacity-60`}
              />
              <button
                type="button"
                onClick={addStarter}
                disabled={
                  !starterDraft.trim() || (draft.conversation_starters ?? []).length >= 5
                }
                className="shrink-0 rounded-md border border-zinc-700 px-3 text-sm text-zinc-200 hover:border-emerald-600 hover:text-emerald-200 disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </div>
        </Field>

        <Field
          label="LLM provider"
          help={lockedLlm ? "This deployment locks the LLM provider." : undefined}
        >
          <select
            value={draft.llm_provider}
            onChange={(e) =>
              setDraft({ ...draft, llm_provider: e.target.value as LLMProvider })
            }
            disabled={lockedLlm !== null}
            className={`${inputClass} disabled:opacity-60`}
          >
            {lockedLlm ? (
              <option value={lockedLlm.provider}>{lockedLlm.provider}</option>
            ) : configuredProviders.length === 0 ? (
              <option value="">— no providers configured (add a key in Settings) —</option>
            ) : (
              configuredProviders.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))
            )}
          </select>
        </Field>

        <Field
          label="LLM model"
          help={
            lockedLlm?.model
              ? "This deployment pins the model alongside the provider."
              : draft.llm_provider === "ollama"
                ? "Required for Ollama — e.g. llama3.1:8b, qwen2.5-coder:14b. Pull it first with `ollama pull <model>`."
                : "Optional. Leave blank to use the provider's SDK default."
          }
        >
          <input
            value={draft.llm_model ?? ""}
            onChange={(e) => setDraft({ ...draft, llm_model: e.target.value || undefined })}
            placeholder={modelPlaceholder(draft.llm_provider)}
            disabled={lockedLlm?.model != null}
            className={`${inputClass} font-mono disabled:opacity-60`}
          />
        </Field>

        <Field label="Storage backend">
          <select
            value={draft.storage_kind}
            onChange={(e) =>
              setDraft({
                ...draft,
                storage_kind: e.target.value as StorageKind,
                storage_url: e.target.value === "sqlite" ? undefined : draft.storage_url,
              })
            }
            className={inputClass}
          >
            <option value="sqlite">SQLite (local file, default)</option>
            <option value="postgres">Postgres (durable, multi-process)</option>
          </select>
        </Field>

        {draft.storage_kind === "postgres" && (
          <Field
            label="Postgres connection URL"
            help="Format: postgresql://user:pass@host:5432/dbname"
            required
          >
            <input
              value={draft.storage_url ?? ""}
              onChange={(e) => setDraft({ ...draft, storage_url: e.target.value || undefined })}
              placeholder="postgresql://user:pass@localhost:5432/wisdom_studio"
              className={`${inputClass} font-mono`}
            />
          </Field>
        )}

        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500 disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create agent"}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none";

function modelPlaceholder(provider: LLMProvider): string {
  switch (provider) {
    case "anthropic":
      return "claude-haiku-4-5  (fast + cheap default; upgrade to sonnet/opus later)";
    case "openai":
      return "gpt-5-mini";
    case "gemini":
      return "gemini-2.5-flash";
    case "ollama":
      return "llama3.2:3b  (or gemma3:4b, phi4-mini)";
    case "litellm":
      return "claude-haiku-4-5  (or any LiteLLM model id)";
  }
}

function Field(props: {
  label: string;
  help?: string;
  required?: boolean;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-zinc-300">
        {props.label}
        {props.required && <span className="ml-1 text-emerald-400">*</span>}
      </span>
      {props.children}
      {props.help && <p className="mt-1 text-xs text-zinc-500">{props.help}</p>}
    </label>
  );
}
