"""Agent 2 — Next.js Developer: file parsing and writing utilities.

LLM interaction is handled by CrewAI. This module provides post-processing
for the developer agent's output: parsing code blocks, writing files to disk,
and ensuring required configs exist.
"""

import json
import re
import logging

import agent.config as cfg

logger = logging.getLogger("agent.generator")

_PATH_EXT = (".tsx", ".ts", ".jsx", ".js", ".css", ".json", ".mjs", ".cjs")
_LANG_TAGS = frozenset(
    {
        "",
        "ts",
        "tsx",
        "typescript",
        "js",
        "jsx",
        "javascript",
        "css",
        "json",
        "text",
    }
)


def _is_rel_path_tag(tag: str) -> bool:
    t = (tag or "").strip()
    if not t or t in _LANG_TAGS:
        return False
    if "/" in t or t.endswith(_PATH_EXT):
        return True
    return False


def _strip_inline_path_comment(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return content
    first = lines[0].strip()
    if re.match(r"^(//|#)\s*(file|path)\s*:\s*\S+", first, re.I):
        return "\n".join(lines[1:]).lstrip("\n")
    return content


def _path_from_prose_before(raw: str, fence_start: int) -> str | None:
    before = raw[:fence_start].rstrip()
    lines = [ln.strip() for ln in before.splitlines() if ln.strip()]
    for ln in reversed(lines[-8:]):
        m = re.search(r"`([^`]+\.(?:tsx?|jsx?|css|json))`", ln)
        if m:
            p = m.group(1).strip().strip("*")
            if p:
                return p
        m = re.search(
            r"(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.(?:tsx?|jsx?|css|json))(?:\s*[`*]*\s*)?$",
            ln,
        )
        if m:
            return m.group(1).strip()
        m = re.search(r"\(([\w./]+\.(?:tsx?|jsx?|css|json))\)", ln)
        if m:
            return m.group(1).strip()
    return None


def parse_files_from_response(raw: str) -> dict[str, str]:
    """Extract file path -> content pairs from LLM response.

    Expects ```filepath\\ncontent\\n``` blocks, language-only fences with a path
    on a nearby prose line, or a JSON dict.
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
    pattern = r"```([^\n`]*)\n(.*?)```"
    for match in re.finditer(pattern, raw, re.DOTALL):
        tag = (match.group(1) or "").strip()
        content = match.group(2).strip()
        content = _strip_inline_path_comment(content)

        filepath: str | None = None
        if _is_rel_path_tag(tag):
            filepath = tag
        else:
            filepath = _path_from_prose_before(raw, match.start())

        if filepath and ("/" in filepath or filepath.endswith(_PATH_EXT)):
            files[filepath] = content

    if not files:
        raise ValueError("Could not parse any files from LLM response")

    return files


def materialize_site_from_raw(raw: str, *, reset_output_dir: bool = True) -> dict[str, object]:
    """Parse LLM output, ensure boilerplate, write under cfg.OUTPUT_DIR.

    Shared by the write_website_files tool and the pipeline fallback.
    """
    import shutil

    if reset_output_dir:
        if cfg.OUTPUT_DIR.exists():
            shutil.rmtree(cfg.OUTPUT_DIR)
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parsed = parse_files_from_response(raw)
    parsed = ensure_package_json(parsed)
    parsed = ensure_configs(parsed)
    written = write_files(parsed)
    return {"files_written": len(written), "paths": written}


def write_files(files: dict[str, str]) -> list[str]:
    """Write generated files to OUTPUT_DIR. Returns list of written paths."""
    written: list[str] = []
    for rel_path, content in files.items():
        full = cfg.OUTPUT_DIR / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        snippet_lines = (content or "").splitlines()[:14]
        snippet = "\n".join(snippet_lines)
        logger.info(
            "[code] writing %s\n%s%s",
            rel_path,
            snippet,
            "\n... (truncated)" if len((content or "").splitlines()) > 14 else "",
        )
        full.write_text(content, encoding="utf-8")
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
