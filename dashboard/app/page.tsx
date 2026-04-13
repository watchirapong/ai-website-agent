"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PromptInput from "@/components/PromptInput";
import PipelineLogPanel from "@/components/PipelineLogPanel";
import ProgressTracker from "@/components/ProgressTracker";
import ScoreCards from "@/components/ScoreCards";
import ScreenshotGrid from "@/components/ScreenshotGrid";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8020";
/** Remember last run so refresh can reload progress from the API */
const STORAGE_KEY = "aiagent_active_project";

interface PipelineEvent {
  seq?: number;
  timestamp?: string;
  step: string;
  status: string;
  detail: Record<string, unknown>;
}

interface StatusResponse {
  status?: string;
  error?: string | null;
  attempts?: number;
  time_seconds?: number;
  events?: PipelineEvent[];
}

type StreamMode =
  | "stream"
  | "polling"
  | "idle"
  | "connecting"
  | "cancelling";

function normalizeEvents(raw: PipelineEvent[]): PipelineEvent[] {
  return raw.map((e) => ({
    seq: typeof e.seq === "number" ? e.seq : undefined,
    timestamp: typeof e.timestamp === "string" ? e.timestamp : undefined,
    step: e.step,
    status: e.status,
    detail: (e.detail || {}) as Record<string, unknown>,
  }));
}

function formatEventLine(event: PipelineEvent): string {
  const ts = event.timestamp
    ? new Date(event.timestamp).toLocaleTimeString()
    : "";
  const prefix = ts ? `[${ts}]` : "[event]";

  if (event.step === "log" && event.status === "line") {
    return `${prefix} ${String(event.detail?.message ?? "")}`;
  }

  let detailText = "";
  const detail = event.detail || {};
  if (Object.keys(detail).length > 0) {
    try {
      detailText = ` | detail=${JSON.stringify(detail)}`;
    } catch {
      detailText = " | detail=[unserializable]";
    }
  }

  const seqText = typeof event.seq === "number" ? `#${event.seq} ` : "";
  return `${prefix} ${seqText}[${event.step}] ${event.status}${detailText}`;
}

function isTerminalPipeline(evs: PipelineEvent[]): boolean {
  return evs.some(
    (e) =>
      e.step === "pipeline" &&
      (e.status === "complete" || e.status === "failed")
  );
}

function isTerminalStatus(status?: string): boolean {
  return status === "completed" || status === "failed";
}

function mergeEventsBySeq(
  prev: PipelineEvent[],
  incoming: PipelineEvent[]
): PipelineEvent[] {
  if (incoming.length === 0) return prev;
  const map = new Map<number, PipelineEvent>();
  const noSeq: PipelineEvent[] = [];
  for (const event of prev) {
    if (typeof event.seq === "number") map.set(event.seq, event);
    else noSeq.push(event);
  }
  for (const event of incoming) {
    if (typeof event.seq === "number") map.set(event.seq, event);
    else noSeq.push(event);
  }
  const ordered = Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map((entry) => entry[1]);
  return [...ordered, ...noSeq];
}

function getLastSeq(events: PipelineEvent[]): number {
  for (let i = events.length - 1; i >= 0; i--) {
    if (typeof events[i].seq === "number") return events[i].seq as number;
  }
  return 0;
}

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  return fallback;
}

function attachEventSource(
  id: string,
  afterSeq: number,
  opts: {
    onEvent: (e: PipelineEvent) => void;
    onDone: (detail: Record<string, unknown>) => void;
    onStreamError: (reason: string) => void;
  }
) {
  const q = afterSeq > 0 ? `?after_seq=${afterSeq}` : "";
  const evtSource = new EventSource(
    `${API_URL}/api/status/${id}/stream${q}`
  );
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
    opts.onStreamError("EventSource disconnected");
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
  const [streamMode, setStreamMode] = useState<StreamMode>("idle");
  const [approvingStep, setApprovingStep] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const closeStreamRef = useRef<(() => void) | null>(null);
  /** When status is `stopping`, track how long — auto-clear if server never finishes */
  const stoppingSinceRef = useRef<number | null>(null);

  const handleStartOver = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    (closeStreamRef.current as (() => void) | null)?.();
    closeStreamRef.current = null;
    stoppingSinceRef.current = null;
    setProjectId(null);
    setEvents([]);
    setResult(null);
    setError(null);
    setIsRunning(false);
    setStreamMode("idle");
  };

  /** After refresh: reload events from API (in-memory on server) or poll until the run ends */
  useEffect(() => {
    if (typeof window === "undefined") return;

    const id = sessionStorage.getItem(STORAGE_KEY);
    if (!id) return;

    let cancelled = false;

    const applySnapshot = (data: StatusResponse) => {
      const evs = normalizeEvents(data.events || []);
      setProjectId(id);
      setEvents((prev) => mergeEventsBySeq(prev, evs));
      if (isTerminalStatus(data.status)) {
        stoppingSinceRef.current = null;
        setResult({
          error: data.status === "failed" ? data.error || "Pipeline failed" : null,
          attempts: data.attempts || 0,
          time_seconds: data.time_seconds || 0,
        });
        setIsRunning(false);
        setStreamMode("idle");
        sessionStorage.removeItem(STORAGE_KEY);
        return true;
      }
      if (isTerminalPipeline(evs)) {
        stoppingSinceRef.current = null;
        const last = [...evs].reverse().find((e) => e.step === "pipeline");
        if (last) setResult(last.detail as Record<string, unknown>);
        setIsRunning(false);
        setStreamMode("idle");
        sessionStorage.removeItem(STORAGE_KEY);
        return true;
      }
      if (data.status === "stopping") {
        if (stoppingSinceRef.current === null) stoppingSinceRef.current = Date.now();
        const elapsed = Date.now() - stoppingSinceRef.current;
        if (elapsed > 45_000) {
          stoppingSinceRef.current = null;
          sessionStorage.removeItem(STORAGE_KEY);
          setIsRunning(false);
          setStreamMode("idle");
          setProjectId(null);
          setEvents([]);
          setError(
            "Previous job stayed in “stopping” too long — session cleared. You can generate again."
          );
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          return true;
        }
        setIsRunning(false);
        setStreamMode("cancelling");
        return false;
      }
      stoppingSinceRef.current = null;
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
        const data = (await res.json()) as StatusResponse;
        if (cancelled) return;
        if (applySnapshot(data)) return;

        pollRef.current = setInterval(async () => {
          try {
            const r = await fetch(`${API_URL}/api/status/${id}`);
            if (!r.ok) return;
            const d = (await r.json()) as StatusResponse;
            if (applySnapshot(d)) {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } catch {
            /* ignore */
          }
        }, 2000);
      } catch {
        setError(`Cannot reach backend API at ${API_URL}`);
        sessionStorage.removeItem(STORAGE_KEY);
      }
    })();

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      (closeStreamRef.current as (() => void) | null)?.();
    };
  }, []);

  const handleGenerate = async (prompt: string) => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (closeStreamRef.current) {
      (closeStreamRef.current as (() => void) | null)?.();
      closeStreamRef.current = null;
    }
    setEvents([]);
    setResult(null);
    setError(null);
    setStreamMode("connecting");
    setApprovingStep(null);
    setIsRunning(true);

    try {
      const res = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, manual_approval: false }),
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
        (closeStreamRef.current as (() => void) | null)?.();
        closeStreamRef.current = null;
      }

      /** Hydrate from REST so UI updates even if EventSource fails (firewall, browser, etc.) */
      let afterSeq = 0;
      try {
        const snapRes = await fetch(`${API_URL}/api/status/${id}`);
        if (snapRes.ok) {
          const snap = (await snapRes.json()) as StatusResponse;
          if (isTerminalStatus(snap.status)) {
            setResult({
              error:
                snap.status === "failed"
                  ? snap.error || "Pipeline failed"
                  : null,
              attempts: snap.attempts || 0,
              time_seconds: snap.time_seconds || 0,
            });
            setIsRunning(false);
            setStreamMode("idle");
            sessionStorage.removeItem(STORAGE_KEY);
            return;
          }
          const evs = normalizeEvents(snap.events || []);
          setEvents((prev) => mergeEventsBySeq(prev, evs));
          afterSeq = getLastSeq(evs);
          if (isTerminalPipeline(evs)) {
            const last = [...evs].reverse().find((e) => e.step === "pipeline");
            if (last) setResult(last.detail as Record<string, unknown>);
            setIsRunning(false);
            setStreamMode("idle");
            sessionStorage.removeItem(STORAGE_KEY);
            return;
          }
        }
      } catch {
        setError(`Status snapshot failed. Trying live stream... API: ${API_URL}`);
      }

      const startPollFallback = (reason: string) => {
        if (pollRef.current) return;
        setStreamMode("polling");
        setError(
          (prev: string | null) =>
            prev ||
            `Live stream unavailable (${reason}) — refreshing via HTTP. API: ${API_URL}`
        );
        pollRef.current = setInterval(async () => {
          try {
            const r = await fetch(`${API_URL}/api/status/${id}`);
            if (!r.ok) return;
            const d = (await r.json()) as StatusResponse;
            if (isTerminalStatus(d.status)) {
              setResult({
                error:
                  d.status === "failed" ? d.error || "Pipeline failed" : null,
                attempts: d.attempts || 0,
                time_seconds: d.time_seconds || 0,
              });
              setIsRunning(false);
              setStreamMode("idle");
              sessionStorage.removeItem(STORAGE_KEY);
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
              return;
            }
            const evs = normalizeEvents(d.events || []);
            setEvents((prev) => mergeEventsBySeq(prev, evs));
            if (isTerminalPipeline(evs)) {
              const last = [...evs].reverse().find((e) => e.step === "pipeline");
              if (last) setResult(last.detail as Record<string, unknown>);
              setIsRunning(false);
              setStreamMode("idle");
              sessionStorage.removeItem(STORAGE_KEY);
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } catch (pollErr) {
            setError(
              `HTTP polling failed: ${toErrorMessage(pollErr, "unknown error")}`
            );
          }
        }, 1500);
      };

      setStreamMode("stream");
      closeStreamRef.current = attachEventSource(id, afterSeq, {
        onEvent: (event) =>
          setEvents((prev) => mergeEventsBySeq(prev, [event])),
        onDone: (detail) => {
          setResult(detail);
          setIsRunning(false);
          setStreamMode("idle");
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        },
        onStreamError: (reason) => {
          startPollFallback(reason);
        },
      });
    } catch (e) {
      setError(`Generate request failed: ${toErrorMessage(e, "unknown error")}`);
      setIsRunning(false);
      setStreamMode("idle");
    }
  };

  const handleStop = async () => {
    if (!projectId) return;
    try {
      const res = await fetch(`${API_URL}/api/stop/${projectId}`, { method: "POST" });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      setStreamMode("cancelling");
      setIsRunning(false);
      setError(
        "Stop sent. You can start a new generate below; the old run will finish cancelling on the server."
      );
    } catch (e) {
      setError(`Stop request failed: ${toErrorMessage(e, "unknown error")}`);
    }
  };

  const handleApproveStep = async (step: string) => {
    if (!projectId || approvingStep) return;
    setApprovingStep(step);
    try {
      const res = await fetch(`${API_URL}/api/approve/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve request failed");
    } finally {
      setApprovingStep(null);
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
      events.map((e) => formatEventLine(e)),
    [events]
  );
  const codeLines = useMemo(
    () => logLines.filter((l) => l.includes("[code]")),
    [logLines]
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
        <PromptInput onSubmit={handleGenerate} onStop={handleStop} isLoading={isRunning} />
        {(isRunning || streamMode === "cancelling") && (
          <p className="mt-2 text-xs text-gray-500">
            Connection mode:{" "}
            {streamMode === "cancelling"
              ? "stop requested — you can generate again below; old run ends in the background"
              : streamMode === "connecting"
                ? "connecting…"
                : streamMode === "stream"
                  ? "live stream"
                  : streamMode === "polling"
                    ? "HTTP polling fallback"
                    : "idle"}
          </p>
        )}
        {projectId && !isRunning && (
          <p className="mt-2 text-xs text-gray-500">
            <button
              type="button"
              onClick={handleStartOver}
              className="text-blue-400 underline decoration-blue-400/50 hover:text-blue-300"
            >
              Clear session / reset form
            </button>
            <span className="text-gray-600"> — if the UI looks stuck after a stop or refresh</span>
          </p>
        )}
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

      {(events.length > 0 || (isRunning && projectId)) && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Progress</h2>
          {events.length === 0 && isRunning && (
            <p className="mb-4 text-sm text-gray-500">
              Connecting to the pipeline…
            </p>
          )}
          <ProgressTracker
            events={events}
            onApproveStep={handleApproveStep}
            approvingStep={approvingStep}
          />
        </section>
      )}

      <PipelineLogPanel
        lines={logLines}
        show={!!projectId && (isRunning || logLines.length > 0)}
        waiting={isRunning && logLines.length === 0}
      />

      {!!projectId && (isRunning || codeLines.length > 0) && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Live Code Stream</h2>
          <p className="mb-2 text-xs text-gray-500">
            Real-time snippets of files as the AI writes them.
          </p>
          <pre className="max-h-[24rem] overflow-auto rounded-lg border border-gray-800 bg-black/60 p-4 font-mono text-[11px] leading-relaxed text-gray-300">
            {(codeLines.length > 0
              ? codeLines.join("\n")
              : "Waiting for code output...")}
          </pre>
        </section>
      )}

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
