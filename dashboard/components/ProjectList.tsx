"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Project {
  id: string;
  prompt: string;
  status: string;
  scores: number | Record<string, unknown>;
  deployed_url: string | null;
  attempts: number;
  time_seconds: number;
  created_at: string;
}

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/projects`)
      .then((res) => res.json())
      .then((data) => {
        setProjects(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-blue-400" />
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 bg-[#141414] p-10 text-center">
        <p className="text-gray-500">No projects yet. Generate your first website!</p>
      </div>
    );
  }

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      completed: "bg-green-500/20 text-green-400",
      started: "bg-blue-500/20 text-blue-400",
      failed: "bg-red-500/20 text-red-400",
      reviewing: "bg-yellow-500/20 text-yellow-400",
    };
    return (
      <span
        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
          colors[status] || "bg-gray-700 text-gray-400"
        }`}
      >
        {status}
      </span>
    );
  };

  const handleDelete = async (id: string) => {
    await fetch(`${API_URL}/api/projects/${id}`, { method: "DELETE" });
    setProjects((prev) => prev.filter((p) => p.id !== id));
  };

  return (
    <div className="overflow-hidden rounded-xl border border-gray-800">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-800 bg-[#141414]">
          <tr>
            <th className="px-5 py-3 font-medium text-gray-400">Prompt</th>
            <th className="px-5 py-3 font-medium text-gray-400">Status</th>
            <th className="px-5 py-3 font-medium text-gray-400">Score</th>
            <th className="px-5 py-3 font-medium text-gray-400">URL</th>
            <th className="px-5 py-3 font-medium text-gray-400">Time</th>
            <th className="px-5 py-3 font-medium text-gray-400"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {projects.map((p) => (
            <tr key={p.id} className="transition hover:bg-[#1a1a1a]">
              <td className="max-w-xs truncate px-5 py-3 text-gray-300">
                {p.prompt}
              </td>
              <td className="px-5 py-3">{statusBadge(p.status)}</td>
              <td className="px-5 py-3 text-gray-300">
                {typeof p.scores === "number" ? p.scores : "—"}
              </td>
              <td className="px-5 py-3">
                {p.deployed_url ? (
                  <a
                    href={p.deployed_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 underline hover:text-blue-300"
                  >
                    Link
                  </a>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
              </td>
              <td className="px-5 py-3 text-gray-500">
                {p.time_seconds ? `${p.time_seconds}s` : "—"}
              </td>
              <td className="px-5 py-3">
                <button
                  onClick={() => handleDelete(p.id)}
                  className="text-xs text-gray-600 transition hover:text-red-400"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
