"use client";

import { useState } from "react";
import PromptInput from "@/components/PromptInput";
import ProgressTracker from "@/components/ProgressTracker";
import ScoreCards from "@/components/ScoreCards";
import ScreenshotGrid from "@/components/ScreenshotGrid";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PipelineEvent {
  step: string;
  status: string;
  detail: Record<string, unknown>;
}

export default function HomePage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const handleGenerate = async (prompt: string) => {
    setEvents([]);
    setResult(null);
    setIsRunning(true);

    try {
      const res = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      const data = await res.json();
      const id = data.project_id;
      setProjectId(id);

      const evtSource = new EventSource(
        `${API_URL}/api/status/${id}/stream`
      );

      evtSource.onmessage = (e) => {
        try {
          const event: PipelineEvent = JSON.parse(e.data);
          setEvents((prev) => [...prev, event]);

          if (
            event.step === "pipeline" &&
            (event.status === "complete" || event.status === "failed")
          ) {
            setResult(event.detail);
            setIsRunning(false);
            evtSource.close();
          }
        } catch {
          // skip malformed events
        }
      };

      evtSource.onerror = () => {
        setIsRunning(false);
        evtSource.close();
      };
    } catch {
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
      </section>

      {events.length > 0 && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Progress</h2>
          <ProgressTracker events={events} />
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
        <section className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-6">
          <h2 className="mb-2 text-lg font-semibold text-yellow-400">
            Pipeline Complete
          </h2>
          <p className="text-sm text-yellow-200">
            Finished in {(result as Record<string, unknown>).time_seconds as number || 0}s
            {" — "}
            {(result as Record<string, unknown>).attempts as number || 0} attempt(s)
          </p>
        </section>
      )}
    </div>
  );
}
