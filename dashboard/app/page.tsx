"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PromptInput from "@/components/PromptInput";
import PipelineLogPanel from "@/components/PipelineLogPanel";
import ProgressTracker from "@/components/ProgressTracker";
import ScoreCards from "@/components/ScoreCards";
import ScreenshotGrid from "@/components/ScreenshotGrid";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
/** Remember last run so refresh can reload progress from the API */
const STORAGE_KEY = "aiagent_active_project";

interface PipelineEvent {
  step: string;
  status: string;
  detail: Record<string, unknown>;
}

function attachEventSource(
  id: string,
  opts: {
    onEvent: (e: PipelineEvent) => void;
    onDone: (detail: Record<string, unknown>) => void;
    onStreamError: () => void;
  }
) {
  const evtSource = new EventSource(`${API_URL}/api/status/${id}/stream`);
  const finished = { current: false };

  evtSource.onmessage = (e) => {
    try {
      const event: PipelineEvent = JSON.parse(e.data);
      opts.onEvent(event);
      if (
        event.step === "pipeline" &&
        (event.status === "complete" || event.status === "failed")
      ) {
        finished.current = true;
        opts.onDone(event.detail as Record<string, unknown>);
        evtSource.close();
      }
    } catch {
      // skip malformed events
    }
  };

  evtSource.onerror = () => {
    if (finished.current) return;
    opts.onStreamError();
    evtSource.close();
  };

  return () => evtSource.close();
}

export default function HomePage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const closeStreamRef = useRef<(() => void) | null>(null);

  /** After refresh: reload events from API (in-memory on server) or poll until the run ends */
  useEffect(() => {
    if (typeof window === "undefined") return;

    const id = sessionStorage.getItem(STORAGE_KEY);
    if (!id) return;

    let cancelled = false;

    const applySnapshot = (raw: PipelineEvent[]) => {
      const evs = raw.map((e) => ({
        step: e.step,
        status: e.status,
        detail: (e.detail || {}) as Record<string, unknown>,
      }));
      setProjectId(id);
      setEvents(evs);
      const terminal = evs.some(
        (e) =>
          e.step === "pipeline" &&
          (e.status === "complete" || e.status === "failed")
      );
      if (terminal) {
        const last = [...evs].reverse().find((e) => e.step === "pipeline");
        if (last) setResult(last.detail as Record<string, unknown>);
        setIsRunning(false);
        return true;
      }
      setIsRunning(true);
      return false;
    };

    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/status/${id}`);
        if (!res.ok) {
          sessionStorage.removeItem(STORAGE_KEY);
          return;
        }
        const data = (await res.json()) as { events?: PipelineEvent[] };
        if (cancelled) return;
        const raw = data.events || [];
        if (applySnapshot(raw)) return;

        pollRef.current = setInterval(async () => {
          try {
            const r = await fetch(`${API_URL}/api/status/${id}`);
            if (!r.ok) return;
            const d = (await r.json()) as { events?: PipelineEvent[] };
            if (applySnapshot(d.events || [])) {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } catch {
            /* ignore */
          }
        }, 2000);
      } catch {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    })();

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      if (closeStreamRef.current) closeStreamRef.current();
    };
  }, []);

  const handleGenerate = async (prompt: string) => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (closeStreamRef.current) {
      closeStreamRef.current();
      closeStreamRef.current = null;
    }
    setEvents([]);
    setResult(null);
    setError(null);
    setIsRunning(true);

    try {
      const res = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const id = data.project_id;
      setProjectId(id);
      sessionStorage.setItem(STORAGE_KEY, id);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      if (closeStreamRef.current) {
        closeStreamRef.current();
        closeStreamRef.current = null;
      }

      closeStreamRef.current = attachEventSource(id, {
        onEvent: (event) =>
          setEvents((prev) => [...prev, event]),
        onDone: (detail) => {
          setResult(detail);
          setIsRunning(false);
        },
        onStreamError: () => {
          setError(
            "Lost connection to progress stream. Is the API running on " +
              API_URL +
              "?"
          );
          setIsRunning(false);
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setIsRunning(false);
    }
  };

  const latestLighthouse = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.step === "tester" && e.status === "done") {
        const report = e.detail?.report as Record<string, unknown> | undefined;
        return report?.lighthouse as Record<string, number> | undefined;
      }
    }
    return null;
  })();

  const deployedUrl = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.step === "deployer" && e.status === "done") {
        return e.detail?.url as string | undefined;
      }
    }
    return null;
  })();

  const logLines = useMemo(
    () =>
      events
        .filter((e) => e.step === "log" && e.status === "line")
        .map((e) => String(e.detail?.message ?? "")),
    [events]
  );

  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-2 text-3xl font-bold tracking-tight">
          Generate a Website
        </h1>
        <p className="mb-6 text-gray-400">
          Describe the website you want. The AI will build, test, and deploy it
          automatically.
        </p>
        <PromptInput onSubmit={handleGenerate} isLoading={isRunning} />
        <p className="mt-4 text-xs text-gray-500">
          Full stderr/stdout still appears in the{" "}
          <code className="rounded bg-gray-800 px-1 py-0.5">uvicorn</code>{" "}
          terminal. Refreshing reconnects to the last run if the API still has
          it in memory.
        </p>
        {error && (
          <p className="mt-4 rounded-lg border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        )}
      </section>

      {events.length > 0 && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Progress</h2>
          <ProgressTracker events={events} />
        </section>
      )}

      <PipelineLogPanel
        lines={logLines}
        show={!!projectId && (isRunning || logLines.length > 0)}
        waiting={isRunning && logLines.length === 0}
      />

      {latestLighthouse && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Scores</h2>
          <ScoreCards lighthouse={latestLighthouse} />
        </section>
      )}

      <section>
        <ScreenshotGrid projectId={projectId} show={!!latestLighthouse} />
      </section>

      {deployedUrl && (
        <section className="rounded-xl border border-green-800 bg-green-950/40 p-6">
          <h2 className="mb-2 text-lg font-semibold text-green-400">
            Deployed Successfully
          </h2>
          <a
            href={deployedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-300 underline transition hover:text-green-100"
          >
            {deployedUrl}
          </a>
        </section>
      )}

      {result && !deployedUrl && !isRunning && (
        <section
          className={
            (result as Record<string, unknown>).error != null
              ? "rounded-xl border border-red-800 bg-red-950/40 p-6"
              : "rounded-xl border border-yellow-800 bg-yellow-950/40 p-6"
          }
        >
          <h2
            className={
              (result as Record<string, unknown>).error != null
                ? "mb-2 text-lg font-semibold text-red-400"
                : "mb-2 text-lg font-semibold text-yellow-400"
            }
          >
            {(result as Record<string, unknown>).error != null
              ? "Pipeline failed"
              : "Pipeline finished"}
          </h2>
          {(result as Record<string, unknown>).error != null ? (
            <p className="text-sm text-red-100 whitespace-pre-wrap break-words">
              {String((result as Record<string, unknown>).error)}
            </p>
          ) : (
            <p className="text-sm text-yellow-200">
              Finished in{" "}
              {(result as Record<string, unknown>).time_seconds as number || 0}s
              {" — "}
              {(result as Record<string, unknown>).attempts as number || 0}{" "}
              attempt(s)
            </p>
          )}
        </section>
      )}
    </div>
  );
}
