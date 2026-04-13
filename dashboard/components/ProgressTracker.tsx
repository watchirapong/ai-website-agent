"use client";

interface PipelineEvent {
  step: string;
  status: string;
  detail: Record<string, unknown>;
}

interface Props {
  events: PipelineEvent[];
}

const STEPS = [
  { key: "planner", label: "Planner", icon: "1" },
  { key: "developer", label: "Developer", icon: "2" },
  { key: "build", label: "Build", icon: "3" },
  { key: "server", label: "Server", icon: "4" },
  { key: "tester", label: "Tester", icon: "5" },
  { key: "reviewer", label: "Reviewer", icon: "6" },
  { key: "deployer", label: "Deployer", icon: "7" },
];

function getStepStatus(
  stepKey: string,
  events: PipelineEvent[]
): "pending" | "running" | "done" | "failed" {
  let latest: string = "pending";
  for (const e of events) {
    if (e.step === stepKey) {
      if (e.status === "running") latest = "running";
      else if (e.status === "done") latest = "done";
      else if (e.status === "failed") latest = "failed";
    }
  }
  return latest as "pending" | "running" | "done" | "failed";
}

function getStepDetail(stepKey: string, events: PipelineEvent[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.step !== stepKey) continue;

    if (stepKey === "planner" && e.status === "done") {
      const plan = e.detail?.plan as Record<string, unknown> | undefined;
      if (plan) {
        const pages = (plan.pages as unknown[])?.length || 0;
        const comps = (plan.components as unknown[])?.length || 0;
        return `${pages} pages, ${comps} components`;
      }
    }
    if (stepKey === "developer" && e.status === "done") {
      return `${e.detail?.count || 0} files generated`;
    }
    if (stepKey === "build" && e.status === "done") {
      return "Build passed";
    }
    if (stepKey === "build" && e.status === "failed") {
      return "Build failed";
    }
    if (stepKey === "server" && e.status === "done") {
      return String(e.detail?.url || "Started");
    }
    if (stepKey === "tester" && e.status === "done") {
      const report = e.detail?.report as Record<string, unknown> | undefined;
      const lh = report?.lighthouse as Record<string, number> | undefined;
      if (lh) {
        return `perf=${lh.performance} a11y=${lh.accessibility} bp=${lh.best_practices} seo=${lh.seo}`;
      }
    }
    if (stepKey === "reviewer" && e.status === "done") {
      return e.detail?.passed ? "PASS" : "FAIL";
    }
    if (stepKey === "deployer" && e.status === "done") {
      return String(e.detail?.url || "Deployed");
    }
    if (e.status === "failed") {
      return String(e.detail?.error || "Failed").slice(0, 60);
    }
  }
  return "";
}

function getCurrentAttempt(events: PipelineEvent[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].step === "attempt" && events[i].status === "start") {
      return `Attempt ${events[i].detail?.attempt}/${events[i].detail?.max}`;
    }
  }
  return "";
}

export default function ProgressTracker({ events }: Props) {
  const attempt = getCurrentAttempt(events);

  return (
    <div className="space-y-3">
      {attempt && (
        <p className="text-sm font-medium text-blue-400">{attempt}</p>
      )}
      <div className="space-y-2">
        {STEPS.map(({ key, label, icon }) => {
          const status = getStepStatus(key, events);
          const detail = getStepDetail(key, events);

          const ringColor = {
            pending: "border-gray-700 text-gray-600",
            running: "border-blue-500 text-blue-400 animate-pulse",
            done: "border-green-500 bg-green-500/20 text-green-400",
            failed: "border-red-500 bg-red-500/20 text-red-400",
          }[status];

          const textColor = {
            pending: "text-gray-600",
            running: "text-blue-300",
            done: "text-gray-300",
            failed: "text-red-300",
          }[status];

          return (
            <div
              key={key}
              className="flex items-center gap-4 rounded-lg border border-gray-800 bg-[#141414] px-4 py-3"
            >
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-bold ${ringColor}`}
              >
                {status === "done"
                  ? "\u2713"
                  : status === "failed"
                  ? "\u2717"
                  : icon}
              </div>
              <div className="flex-1">
                <span className={`text-sm font-medium ${textColor}`}>
                  {label}
                </span>
                {detail && (
                  <span className="ml-3 text-xs text-gray-500">{detail}</span>
                )}
              </div>
              {status === "running" && (
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-400/30 border-t-blue-400" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
