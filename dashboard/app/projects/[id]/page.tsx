"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ScoreCards from "@/components/ScoreCards";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8020";

interface Project {
  id: string;
  prompt: string;
  status: string;
  scores: number;
  lighthouse: Record<string, number>;
  deployed_url: string | null;
  attempts: number;
  time_seconds: number;
  created_at: string;
}

export default function ProjectDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/projects/${id}`)
      .then((res) => res.json())
      .then((data) => {
        setProject(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-blue-400" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="py-20 text-center text-gray-500">Project not found.</div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <a
          href="/projects"
          className="mb-4 inline-block text-sm text-gray-500 transition hover:text-gray-300"
        >
          &larr; Back to projects
        </a>
        <h1 className="text-2xl font-bold">{project.prompt}</h1>
        <p className="mt-1 text-sm text-gray-500">
          Created {project.created_at} &middot; {project.attempts} attempt(s)
          &middot; {project.time_seconds}s
        </p>
      </div>

      {project.deployed_url && (
        <div className="rounded-xl border border-green-800 bg-green-950/40 p-5">
          <p className="text-sm font-medium text-green-400">Deployed</p>
          <a
            href={project.deployed_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-300 underline hover:text-green-100"
          >
            {project.deployed_url}
          </a>
        </div>
      )}

      {project.lighthouse &&
        typeof project.lighthouse === "object" &&
        Object.keys(project.lighthouse).length > 0 && (
          <ScoreCards lighthouse={project.lighthouse} />
        )}

      <div>
        <h2 className="mb-4 text-xl font-semibold">Screenshots</h2>
        <div className="grid grid-cols-3 gap-4">
          {["desktop", "tablet", "mobile"].map((name) => (
            <div key={name} className="space-y-2">
              <p className="text-center text-xs font-medium capitalize text-gray-500">
                {name}
              </p>
              <div className="overflow-hidden rounded-lg border border-gray-800 bg-[#141414]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`${API_URL}/screenshots/${name}.png`}
                  alt={`${name} screenshot`}
                  className="h-auto w-full"
                  loading="lazy"
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
