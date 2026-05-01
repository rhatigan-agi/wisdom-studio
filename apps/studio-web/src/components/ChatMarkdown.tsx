import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

// Markdown renderer for assistant chat messages. The agent's responses come
// back as text with markdown conventions (bold, lists, inline code, code
// fences) — without rendering those, the user sees raw asterisks. We don't
// add @tailwindcss/typography since most prose styling here is already
// constrained by the bubble width — a handful of element overrides covers it.
//
// User messages stay plain text on purpose: they round-trip exactly what the
// user typed, no surprise formatting.
const COMPONENTS: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-snug">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-zinc-50">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-emerald-300 underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
  h1: ({ children }) => <h1 className="mb-2 mt-1 text-base font-semibold text-zinc-50">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-1 text-sm font-semibold text-zinc-50">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-1 text-sm font-semibold text-zinc-100">{children}</h3>,
  hr: () => <hr className="my-3 border-zinc-700" />,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-zinc-600 pl-3 text-zinc-300">
      {children}
    </blockquote>
  ),
  // The default react-markdown signature for `code` no longer exposes
  // `inline` in v9 — we detect inline by absence of a language class on the
  // parent <pre>. Inline = subtle pill; block = bordered preformatted box.
  code: ({ className, children }) => {
    const isBlock = typeof className === "string" && className.startsWith("language-");
    if (isBlock) {
      return (
        <code className={`${className} block whitespace-pre-wrap break-words font-mono text-[12.5px]`}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-zinc-950/70 px-1 py-0.5 font-mono text-[12.5px] text-amber-200">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto rounded-md border border-zinc-700 bg-zinc-950/80 p-3 last:mb-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full text-left text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-zinc-700 px-2 py-1 font-semibold text-zinc-200">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-zinc-800 px-2 py-1 text-zinc-300">{children}</td>,
};

export function ChatMarkdown(props: { text: string }): JSX.Element {
  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {props.text}
      </ReactMarkdown>
    </div>
  );
}
