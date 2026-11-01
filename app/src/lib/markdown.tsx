// Minimal, safe Markdown rendering (no HTML injection): paragraphs, lists, headings, bold, inline code.
import React from "react";

function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${key}b${i++}`}>{tok.slice(2, -2)}</strong>);
    else out.push(<code key={`${key}c${i++}`}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = (text || "").split("\n");
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((t, i) => <li key={i}>{inline(t, `l${blocks.length}-${i}`)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const ul = /^\s*[-*•]\s+(.*)/.exec(line);
    const ol = /^\s*\d+[.)]\s+(.*)/.exec(line);
    const h = /^(#{1,3})\s+(.*)/.exec(line);
    if (ul || ol) {
      const ordered = !!ol;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((ul || ol)![1]);
      continue;
    }
    flush();
    if (h) {
      const Tag = (`h${h[1].length}` as unknown) as keyof JSX.IntrinsicElements;
      blocks.push(<Tag key={blocks.length}>{inline(h[2], `h${blocks.length}`)}</Tag>);
    } else if (line.trim()) {
      blocks.push(<p key={blocks.length}>{inline(line, `p${blocks.length}`)}</p>);
    }
  }
  flush();
  return <div className="md selectable leading-relaxed">{blocks}</div>;
}
