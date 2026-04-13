"""Agent 2 — Next.js Developer: file parsing and writing utilities.

LLM interaction is handled by CrewAI. This module provides post-processing
for the developer agent's output: parsing code blocks, writing files to disk,
and ensuring required configs exist.
"""

import json
import re
import logging

import agent.config as cfg
from agent.fs_cleanup import reset_output_directory

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
    if _LEADING_BLOCK_PATH.match(first):
        return "\n".join(lines[1:]).lstrip("\n")
    return content


_LEADING_PATH_LINE = re.compile(
    r"^(?://|#)\s*(?:(?:file|path)\s*:\s*)?(`?)([\w./-]+\.(?:tsx?|jsx?|css|json))\1\s*$",
    re.I,
)
_LEADING_BLOCK_PATH = re.compile(
    r"^\s*/\*\s*([\w./-]+\.(?:tsx?|jsx?|css|json))\s*\*/\s*$",
    re.I,
)


def _extract_path_from_leading_comment(content: str) -> tuple[str | None, str]:
    """If the first line is ``// path``, ``# path``, or ``/* path */``, return path and body."""
    lines = content.splitlines()
    if not lines:
        return None, content
    first = lines[0].strip()
    m = _LEADING_PATH_LINE.match(first)
    if not m:
        m = _LEADING_BLOCK_PATH.match(first)
        if not m:
            return None, content
        path = m.group(1).replace("\\", "/")
    else:
        path = m.group(2).replace("\\", "/")
    rest = "\n".join(lines[1:]).lstrip("\n")
    if "/" not in path and not path.endswith(_PATH_EXT):
        return None, content
    return path, rest


def _dict_from_files_array_payload(data: dict) -> dict[str, str] | None:
    """Handle {\"files\": [{\"path\": \"...\", \"content\": \"...\"}, ...]}."""
    arr = data.get("files")
    if not isinstance(arr, list):
        return None
    out: dict[str, str] = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("filepath") or item.get("file")
        content = item.get("content")
        if content is None:
            content = item.get("body") or item.get("code")
        if path and content is not None and isinstance(path, str):
            out[path] = str(content)
    return out if out else None


def _try_parse_json_object_text(text: str) -> dict[str, str] | None:
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    fa = _dict_from_files_array_payload(data)
    if fa:
        return fa
    # flat map: {"app/page.tsx": "..."} only if values are strings and keys look like paths
    if data and all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        if all(
            ("/" in k or k.endswith(_PATH_EXT)) and not k.startswith("site_")
            for k in data
        ):
            return dict(data)
    return None


def _try_parse_fenced_json_blocks(raw: str) -> dict[str, str] | None:
    """Parse ```json ... ``` bodies that contain a files[] manifest (common from local LLMs)."""
    pattern = r"```(?:json)?\s*\r?\n(.*?)```"
    for match in re.finditer(pattern, raw, re.DOTALL | re.IGNORECASE):
        inner = match.group(1).strip()
        got = _try_parse_json_object_text(inner)
        if got:
            return got
    return None


def _single_lang_fence_default_path(raw: str) -> dict[str, str] | None:
    """If the model emits one ```tsx/ts block with no path, map to app/page.tsx."""
    pattern = r"```([^\n`]+)\r?\n(.*?)```"
    matches = list(re.finditer(pattern, raw, re.DOTALL))
    if len(matches) != 1:
        return None
    tag = (matches[0].group(1) or "").strip().lower()
    if tag not in {"tsx", "ts", "jsx", "js", "typescript", "javascript"}:
        return None
    body = _strip_inline_path_comment(matches[0].group(2).strip())
    if len(body) < 20:
        return None
    return {"app/page.tsx": body}


def _path_from_prose_before(raw: str, fence_start: int) -> str | None:
    before = raw[:fence_start].rstrip()
    lines = [ln.strip() for ln in before.splitlines() if ln.strip()]
    for ln in reversed(lines[-12:]):
        m = re.match(r"^#{1,6}\s+`([^`]+\.(?:tsx?|jsx?|css|json))`\s*$", ln)
        if m:
            return m.group(1).strip()
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
    on a nearby prose line, ```json { \"files\": [...] }``` manifests, or a JSON dict.
    """
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            fa = _dict_from_files_array_payload(data)
            if fa:
                return fa
            if "files" in data and isinstance(data["files"], dict):
                return data["files"]
            if data and all(
                isinstance(k, str) and isinstance(v, str) for k, v in data.items()
            ):
                if all(
                    ("/" in k or k.endswith(_PATH_EXT))
                    and not k.startswith(("site_", "pages"))
                    for k in data
                ):
                    return dict(data)
    except (json.JSONDecodeError, ValueError):
        pass

    fenced_json = _try_parse_fenced_json_blocks(raw)
    if fenced_json:
        return fenced_json

    files: dict[str, str] = {}
    pattern = r"```([^\n`]*)\r?\n(.*?)```"
    for match in re.finditer(pattern, raw, re.DOTALL):
        tag = (match.group(1) or "").strip()
        content = match.group(2).strip()
        if tag.lower() == "json":
            got = _try_parse_json_object_text(content)
            if got:
                files.update(got)
            continue

        filepath: str | None = None
        if _is_rel_path_tag(tag):
            filepath = tag
            path2, rest = _extract_path_from_leading_comment(content)
            if path2 and path2.replace("\\", "/") == filepath.replace("\\", "/"):
                content = rest
        else:
            filepath = _path_from_prose_before(raw, match.start())
            path2, rest = _extract_path_from_leading_comment(content)
            if path2:
                filepath = filepath or path2
                content = rest

        content = _strip_inline_path_comment(content)

        if filepath and ("/" in filepath or filepath.endswith(_PATH_EXT)):
            files[filepath] = content

    if not files:
        fallback = _single_lang_fence_default_path(raw)
        if fallback:
            logger.info(
                "[parse] using single-fence fallback for app/page.tsx (%s chars)",
                len(next(iter(fallback.values()))),
            )
            return fallback

    if not files:
        raise ValueError("Could not parse any files from LLM response")

    return files


def _safe_site_title(site_title: str | None) -> str:
    t = (site_title or "Generated site").strip()[:120]
    return t.replace("\\", "/").replace('"', "'")


def _plan_suggests_dark(style: dict | None) -> bool:
    if not style or not isinstance(style, dict):
        return False
    blob = json.dumps(style).lower()
    if "dark" in blob or "slate" in blob or "navy" in blob:
        return True
    sec = str(style.get("secondary_color", "")).strip()
    if sec.startswith("#") and len(sec) >= 7:
        try:
            r = int(sec[1:3], 16)
            g = int(sec[3:5], 16)
            b = int(sec[5:7], 16)
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            if lum < 0.35:
                return True
        except ValueError:
            pass
    return False


def _normalize_loose_paths(files: dict[str, str]) -> None:
    """If the model wrote ``globals.css`` at repo root, move it to ``app/globals.css``."""
    if "globals.css" in files and "app/globals.css" not in files:
        files["app/globals.css"] = files.pop("globals.css")


def _stub_accent(plan_style: dict | None, dark: bool) -> tuple[str, str]:
    """Tailwind arbitrary colors from plan primary, else warm / blue defaults."""
    hex_c = None
    if plan_style and isinstance(plan_style, dict):
        v = plan_style.get("primary_color")
        if isinstance(v, str) and v.startswith("#") and 4 <= len(v) <= 9:
            hex_c = v
    if hex_c:
        return f"text-[{hex_c}]", f"bg-[{hex_c}] hover:opacity-90"
    if dark:
        return "text-amber-400", "bg-amber-500 hover:bg-amber-400"
    return "text-blue-600", "bg-blue-600 hover:bg-blue-500"


def _enhance_default_globals(files: dict[str, str]) -> None:
    """Layer subtle base polish when globals are only Tailwind directives."""
    key = "app/globals.css"
    if key not in files:
        return
    raw = (files[key] or "").strip()
    if not (
        "@tailwind base" in raw
        and "@tailwind components" in raw
        and "@tailwind utilities" in raw
    ):
        return
    if "font-smoothing" in raw or "@layer base" in raw:
        return
    files[key] = (
        "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
        "@layer base {\n"
        "  html {\n"
        "    -webkit-font-smoothing: antialiased;\n"
        "    -moz-osx-font-smoothing: grayscale;\n"
        "  }\n"
        "}\n"
    )


def ensure_minimal_next_app(
    files: dict[str, str],
    *,
    site_title: str | None = None,
    plan_style: dict | None = None,
) -> list[str]:
    """Ensure App Router root route exists. Returns list of paths that were added (stubs)."""
    added: list[str] = []
    title = _safe_site_title(site_title)
    dark = _plan_suggests_dark(plan_style)
    accent_text, accent_btn = _stub_accent(plan_style, dark)

    if "app/layout.tsx" not in files:
        body_cls = (
            "min-h-screen bg-slate-950 text-slate-100"
            if dark
            else "min-h-screen bg-slate-50 text-slate-900"
        )
        files["app/layout.tsx"] = (
            'import { Inter } from "next/font/google";\n'
            'import "./globals.css";\n\n'
            'const inter = Inter({ subsets: ["latin"], display: "swap" });\n\n'
            f"export const metadata = {{\n"
            f'  title: "{title}",\n'
            f'  description: "Crafted with care — portfolio & creative work.",\n'
            f"}};\n\n"
            f"export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{\n"
            f"  return (\n"
            '    <html lang="en" className={inter.className}>\n'
            f'      <body className="{body_cls} antialiased">{{children}}</body>\n'
            f"    </html>\n"
            f"  );\n"
            f"}}\n"
        )
        added.append("app/layout.tsx")

    if "app/page.tsx" not in files:
        if dark:
            page = (
                'import Link from "next/link";\n\n'
                "export default function Page() {\n"
                "  return (\n"
                '    <div className="relative min-h-screen overflow-hidden bg-slate-950">\n'
                '      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(120,119,198,0.35),transparent)]" />\n'
                '      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(251,191,36,0.08),transparent)]" />\n'
                '      <header className="relative z-10 border-b border-white/5 bg-slate-950/70 backdrop-blur-md">\n'
                '        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">\n'
                f'          <span className="text-lg font-semibold tracking-tight text-white">{title}</span>\n'
                '          <nav className="hidden gap-8 text-sm text-slate-400 sm:flex">\n'
                '            <Link href="#work" className="transition hover:text-white">Work</Link>\n'
                '            <Link href="#about" className="transition hover:text-white">About</Link>\n'
                '            <Link href="#contact" className="transition hover:text-white">Contact</Link>\n'
                "          </nav>\n"
                f'          <Link href="#contact" className="rounded-full px-4 py-2 text-sm font-medium text-white transition {accent_btn}">\n'
                "            Let&apos;s talk\n"
                "          </Link>\n"
                "        </div>\n"
                "      </header>\n"
                '      <main className="relative z-10">\n'
                '        <section className="mx-auto max-w-6xl px-6 pb-24 pt-16 sm:pt-24">\n'
                f'          <p className="text-sm font-semibold uppercase tracking-[0.2em] {accent_text}">Portfolio</p>\n'
                '          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl md:text-6xl">\n'
                "            Design and build experiences people remember.\n"
                "          </h1>\n"
                '          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400">\n'
                "            Selected projects, clean typography, and a layout that scales from phone to desktop.\n"
                "          </p>\n"
                f'          <div className="mt-10 flex flex-wrap gap-4">\n'
                f'            <Link href="#work" className="rounded-full px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-black/20 transition {accent_btn}">\n'
                "              View work\n"
                "            </Link>\n"
                '            <Link href="#contact" className="rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:bg-white/5">\n'
                "              Contact\n"
                "            </Link>\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="work" className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-24">\n'
                '          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">Featured</h2>\n'
                '          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">\n'
                "            {[1, 2, 3].map((i) => (\n"
                '              <article\n'
                "                key={i}\n"
                '                className="group rounded-2xl border border-white/10 bg-white/[0.03] p-1 transition hover:border-white/20 hover:bg-white/[0.06]"\n'
                "              >\n"
                '                <div className="overflow-hidden rounded-xl">\n'
                '                  <div className="aspect-[4/3] bg-gradient-to-br from-slate-800 to-slate-900 transition group-hover:scale-[1.02]" />\n'
                "                </div>\n"
                '                <div className="p-5">\n'
                '                  <h3 className="font-semibold text-white">Project {i}</h3>\n'
                '                  <p className="mt-1 text-sm text-slate-500">Brand, UI, and front-end</p>\n'
                "                </div>\n"
                "              </article>\n"
                "            ))}\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="about" className="border-t border-white/5 bg-slate-900/50 py-20">\n'
                '          <div className="mx-auto max-w-6xl px-6">\n'
                '            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">About</h2>\n'
                '            <p className="mt-4 max-w-2xl text-lg leading-relaxed text-slate-400">\n'
                "              This is a starter layout generated when the model did not supply a full\n"
                '              <code className="mx-1 rounded bg-slate-800 px-1.5 py-0.5 text-sm text-slate-300">app/page.tsx</code>\n'
                "              — replace it with your real content anytime.\n"
                "            </p>\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="contact" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-24">\n'
                '          <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-white/[0.07] to-transparent px-8 py-12 text-center sm:px-16">\n'
                '            <h2 className="text-2xl font-bold text-white sm:text-3xl">Start a project</h2>\n'
                '            <p className="mx-auto mt-3 max-w-md text-slate-400">Tell us what you&apos;re building — we&apos;ll take it from here.</p>\n'
                f'            <a href="mailto:hello@example.com" className="mt-8 inline-flex rounded-full px-8 py-3 text-sm font-semibold text-white transition {accent_btn}">\n'
                "              hello@example.com\n"
                "            </a>\n"
                "          </div>\n"
                "        </section>\n"
                "      </main>\n"
                '      <footer className="relative z-10 border-t border-white/5 py-8 text-center text-xs text-slate-600">\n'
                f"        {title} · Built with Next.js\n"
                "      </footer>\n"
                "    </div>\n"
                "  );\n"
                "}\n"
            )
        else:
            page = (
                'import Link from "next/link";\n\n'
                "export default function Page() {\n"
                "  return (\n"
                '    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100">\n'
                '      <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-md">\n'
                '        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">\n'
                f'          <span className="text-lg font-semibold tracking-tight text-slate-900">{title}</span>\n'
                '          <nav className="hidden gap-8 text-sm text-slate-600 sm:flex">\n'
                '            <Link href="#work" className="transition hover:text-slate-900">Work</Link>\n'
                '            <Link href="#about" className="transition hover:text-slate-900">About</Link>\n'
                '            <Link href="#contact" className="transition hover:text-slate-900">Contact</Link>\n'
                "          </nav>\n"
                f'          <Link href="#contact" className="rounded-full px-4 py-2 text-sm font-medium text-white shadow-md transition {accent_btn}">\n'
                "            Contact\n"
                "          </Link>\n"
                "        </div>\n"
                "      </header>\n"
                '      <main>\n'
                '        <section className="mx-auto max-w-6xl px-6 pb-20 pt-16 sm:pt-24">\n'
                f'          <p className="text-sm font-semibold uppercase tracking-[0.2em] {accent_text}">Welcome</p>\n'
                '          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl">\n'
                "            Thoughtful design for the modern web.\n"
                "          </h1>\n"
                '          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">\n'
                "            A clean, responsive starting point — swap in your copy and components when ready.\n"
                "          </p>\n"
                f'          <div className="mt-10 flex flex-wrap gap-4">\n'
                f'            <Link href="#work" className="rounded-full px-6 py-3 text-sm font-semibold text-white shadow-lg transition {accent_btn}">\n'
                "              Explore\n"
                "            </Link>\n"
                '            <Link href="#contact" className="rounded-full border border-slate-200 px-6 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50">\n'
                "              Get in touch\n"
                "            </Link>\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="work" className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-20">\n'
                '          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">Projects</h2>\n'
                '          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">\n'
                "            {[1, 2, 3].map((i) => (\n"
                '              <article key={i} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">\n'
                '                <div className="aspect-[4/3] bg-gradient-to-br from-slate-100 to-slate-200" />\n'
                '                <div className="p-5">\n'
                "                  <h3 className=\"font-semibold text-slate-900\">Project {i}</h3>\n"
                '                  <p className="mt-1 text-sm text-slate-500">Design & development</p>\n'
                "                </div>\n"
                "              </article>\n"
                "            ))}\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="about" className="border-t border-slate-200 bg-white py-16">\n'
                '          <div className="mx-auto max-w-6xl px-6">\n'
                '            <p className="max-w-2xl text-slate-600">\n'
                "              Starter page — add your real app/page.tsx when the model provides it.\n"
                "            </p>\n"
                "          </div>\n"
                "        </section>\n"
                '        <section id="contact" className="mx-auto max-w-6xl px-6 py-20">\n'
                '          <div className="rounded-3xl border border-slate-200 bg-slate-50 px-8 py-12 text-center">\n'
                '            <h2 className="text-2xl font-bold text-slate-900">Let&apos;s work together</h2>\n'
                f'            <a href="mailto:hello@example.com" className="mt-6 inline-flex rounded-full px-8 py-3 text-sm font-semibold text-white transition {accent_btn}">\n'
                "              Email us\n"
                "            </a>\n"
                "          </div>\n"
                "        </section>\n"
                "      </main>\n"
                '      <footer className="border-t border-slate-200 py-8 text-center text-xs text-slate-500">\n'
                f"        {title}\n"
                "      </footer>\n"
                "    </div>\n"
                "  );\n"
                "}\n"
            )
        files["app/page.tsx"] = page
        added.append("app/page.tsx")

    if added:
        _enhance_default_globals(files)

    return added


def _fix_app_page_invalid_children_prop(files: dict[str, str]) -> None:
    """Next.js App Router pages must not take ``children`` like layouts; fixes common LLM mistake."""
    key = "app/page.tsx"
    if key not in files:
        return
    s = files[key]
    if "children" not in s:
        return
    m = re.search(r"export\s+default\s+function\s+Page\s*\(", s)
    if not m:
        return
    open_paren = m.end() - 1
    depth = 0
    close_paren = None
    for k in range(open_paren, len(s)):
        if s[k] == "(":
            depth += 1
        elif s[k] == ")":
            depth -= 1
            if depth == 0:
                close_paren = k
                break
    if close_paren is None:
        return
    params = s[open_paren + 1 : close_paren]
    if "children" not in params:
        return
    s2 = s[:open_paren] + "()" + s[close_paren + 1 :]
    s2 = re.sub(r"\{children\}", "", s2)
    files[key] = s2


def materialize_site_from_raw(
    raw: str,
    *,
    reset_output_dir: bool = True,
    site_name: str | None = None,
    plan_style: dict | None = None,
) -> dict[str, object]:
    """Parse LLM output, ensure boilerplate, write under cfg.OUTPUT_DIR.

    Shared by the write_website_files tool and the pipeline fallback.
    """
    if reset_output_dir:
        resolved = reset_output_directory(cfg.OUTPUT_DIR, stop_api_preview=True)
        if resolved.resolve() != cfg.OUTPUT_DIR.resolve():
            cfg.set_output_dir(resolved)

    parsed = parse_files_from_response(raw)
    _normalize_loose_paths(parsed)
    parsed = ensure_package_json(parsed)
    parsed = ensure_configs(parsed)
    stub_paths = ensure_minimal_next_app(
        parsed, site_title=site_name, plan_style=plan_style
    )
    _fix_app_page_invalid_children_prop(parsed)
    written = write_files(parsed)
    return {
        "files_written": len(written),
        "paths": written,
        "stub_paths": stub_paths,
    }


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
    """Ensure package.json exists and includes ``@types/node`` when using TypeScript."""
    default_dev = {
        "typescript": "^5.6.3",
        "@types/node": "^20.14.0",
        "@types/react": "^18.3.12",
        "@types/react-dom": "^18.3.1",
        "tailwindcss": "^3.4.15",
        "postcss": "^8.4.49",
        "autoprefixer": "^10.4.20",
    }
    if "package.json" not in files:
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
                "devDependencies": default_dev,
            },
            indent=2,
        )
        return files
    try:
        data = json.loads(files["package.json"])
    except (json.JSONDecodeError, TypeError):
        return files
    if not isinstance(data, dict):
        return files
    dev = data.setdefault("devDependencies", {})
    if not isinstance(dev, dict):
        return files
    uses_ts = "typescript" in dev or any(
        k.endswith((".tsx", ".ts")) for k in files
    )
    if uses_ts and "@types/node" not in dev:
        dev["@types/node"] = "^20.14.0"
        files["package.json"] = json.dumps(data, indent=2)
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
        files["app/globals.css"] = (
            "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
            "@layer base {\n"
            "  html {\n"
            "    -webkit-font-smoothing: antialiased;\n"
            "    -moz-osx-font-smoothing: grayscale;\n"
            "  }\n"
            "}\n"
        )

    return files
