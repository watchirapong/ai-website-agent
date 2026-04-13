"use client";

import ProjectList from "@/components/ProjectList";

export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
        <p className="mt-1 text-gray-400">
          All previously generated websites and their results.
        </p>
      </div>
      <ProjectList />
    </div>
  );
}
