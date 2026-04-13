"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8020";

const SCREENS = [
  { name: "Desktop", file: "desktop.png", width: "w-full" },
  { name: "Tablet", file: "tablet.png", width: "w-3/4" },
  { name: "Mobile", file: "mobile.png", width: "w-1/2" },
];

interface Props {
  projectId: string | null;
  show: boolean;
}

export default function ScreenshotGrid({ projectId, show }: Props) {
  if (!show || !projectId) return null;

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold">Screenshots</h2>
      <div className="grid grid-cols-3 gap-4">
        {SCREENS.map(({ name, file }) => (
          <div key={name} className="space-y-2">
            <p className="text-center text-xs font-medium text-gray-500">
              {name}
            </p>
            <div className="overflow-hidden rounded-lg border border-gray-800 bg-[#141414]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_URL}/screenshots/${file}?t=${Date.now()}`}
                alt={`${name} screenshot`}
                className="h-auto w-full"
                loading="lazy"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
