"""Agent 2 — Next.js Developer: file parsing and writing utilities.

LLM interaction is handled by CrewAI. This module provides post-processing
for the developer agent's output: parsing code blocks, writing files to disk,
and ensuring required configs exist.
"""

import json
import re

from agent.config import OUTPUT_DIR


def parse_files_from_response(raw: str) -> dict[str, str]:
    """Extract file path -> content pairs from LLM response.

    Expects ```filepath\\ncontent\\n``` blocks or a JSON dict.
    """
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "files" in data:
            return data["files"]
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    files: dict[str, str] = {}
    pattern = r"```(\S+)\n(.*?)```"
    for match in re.finditer(pattern, raw, re.DOTALL):
        filepath = match.group(1)
        content = match.group(2).strip()
        if "/" in filepath or filepath.endswith((".tsx", ".ts", ".css", ".js", ".json")):
            files[filepath] = content

    if not files:
        raise ValueError("Could not parse any files from LLM response")

    return files


def write_files(files: dict[str, str]) -> list[str]:
    """Write generated files to OUTPUT_DIR. Returns list of written paths."""
    written: list[str] = []
    for rel_path, content in files.items():
        full = OUTPUT_DIR / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        written.append(rel_path)
    return written


def ensure_package_json(files: dict[str, str]) -> dict[str, str]:
    """Add a default package.json if the LLM didn't generate one."""
    if "package.json" in files:
        return files

    files["package.json"] = json.dumps(
        {
            "name": "generated-site",
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
            },
            "dependencies": {
                "next": "14.2.21",
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
            },
            "devDependencies": {
                "typescript": "^5.6.3",
                "@types/react": "^18.3.12",
                "@types/react-dom": "^18.3.1",
                "tailwindcss": "^3.4.15",
                "postcss": "^8.4.49",
                "autoprefixer": "^10.4.20",
            },
        },
        indent=2,
    )
    return files


def ensure_configs(files: dict[str, str]) -> dict[str, str]:
    """Add boilerplate configs if not generated."""
    if "next.config.js" not in files:
        files["next.config.js"] = "/** @type {import('next').NextConfig} */\nconst nextConfig = {}\n\nmodule.exports = nextConfig\n"

    if "tsconfig.json" not in files:
        files["tsconfig.json"] = json.dumps(
            {
                "compilerOptions": {
                    "target": "es5",
                    "lib": ["dom", "dom.iterable", "esnext"],
                    "allowJs": True,
                    "skipLibCheck": True,
                    "strict": True,
                    "noEmit": True,
                    "esModuleInterop": True,
                    "module": "esnext",
                    "moduleResolution": "bundler",
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "jsx": "preserve",
                    "incremental": True,
                    "plugins": [{"name": "next"}],
                    "paths": {"@/*": ["./*"]},
                },
                "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
                "exclude": ["node_modules"],
            },
            indent=2,
        )

    if "tailwind.config.js" not in files:
        files["tailwind.config.js"] = (
            "/** @type {import('tailwindcss').Config} */\n"
            "module.exports = {\n"
            '  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],\n'
            "  theme: { extend: {} },\n"
            "  plugins: [],\n"
            "}\n"
        )

    if "postcss.config.js" not in files:
        files["postcss.config.js"] = (
            "module.exports = {\n"
            "  plugins: {\n"
            "    tailwindcss: {},\n"
            "    autoprefixer: {},\n"
            "  },\n"
            "}\n"
        )

    if "app/globals.css" not in files:
        files["app/globals.css"] = "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n"

    return files
