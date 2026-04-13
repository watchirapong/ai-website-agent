"use client";

import { useState } from "react";

interface Props {
  onSubmit: (prompt: string) => void;
  onStop?: () => void;
  isLoading: boolean;
}

export default function PromptInput({ onSubmit, onStop, isLoading }: Props) {
  const [prompt, setPrompt] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (trimmed && !isLoading) {
      onSubmit(trimmed);
    }
  };

  const examples = [
    "Build a coffee shop site with menu and contact page",
    "Create a portfolio website with dark theme and project gallery",
    "Make a restaurant landing page with reservation form",
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="relative">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the website you want to build..."
          rows={3}
          className="w-full resize-none rounded-xl border border-gray-700 bg-[#1a1a1a] px-5 py-4 text-base text-white placeholder-gray-500 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          disabled={isLoading}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {examples.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setPrompt(ex)}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 transition hover:border-gray-500 hover:text-gray-200"
              disabled={isLoading}
            >
              {ex.length > 40 ? ex.slice(0, 40) + "..." : ex}
            </button>
          ))}
        </div>

        <button
          type={isLoading ? "button" : "submit"}
          onClick={isLoading ? onStop : undefined}
          disabled={isLoading ? !onStop : !prompt.trim()}
          className={`rounded-xl px-8 py-3 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-40 ${
            isLoading
              ? "bg-red-600 hover:bg-red-500"
              : "bg-blue-600 hover:bg-blue-500"
          }`}
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              Stop
            </span>
          ) : (
            "Generate"
          )}
        </button>
      </div>
    </form>
  );
}
