"use client";

import { useEffect, useRef } from "react";

const MAX_LINES = 1500;

interface Props {
  lines: string[];
  show: boolean;
  waiting?: boolean;
}

export default function PipelineLogPanel({
  lines,
  show,
  waiting = false,
}: Props) {
  const preRef = useRef<HTMLPreElement>(null);
  const trimmed = lines.slice(-MAX_LINES);
  const display =
    trimmed.length > 0
      ? trimmed.join("\n")
      : waiting
        ? "Waiting for log output…"
        : "";

  useEffect(() => {
    const el = preRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [trimmed.length, trimmed[trimmed.length - 1], waiting]);

  if (!show) return null;
  if (trimmed.length === 0 && !waiting) return null;

  return (
    <section>
      <h2 className="mb-4 text-xl font-semibold">Server log</h2>
      <p className="mb-2 text-xs text-gray-500">
        Full pipeline event stream (steps, statuses, and details) from this run.
        Last {MAX_LINES} lines shown.
      </p>
      <pre
        ref={preRef}
        className="max-h-[28rem] overflow-auto rounded-lg border border-gray-800 bg-black/60 p-4 font-mono text-[11px] leading-relaxed text-gray-300"
      >
        {display}
      </pre>
    </section>
  );
}
