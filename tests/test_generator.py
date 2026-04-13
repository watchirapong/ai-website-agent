"""Unit tests for agent.generator (parse + materialize)."""

import json
import shutil
import unittest
from pathlib import Path

import agent.config as cfg
from agent.generator import (
    ensure_minimal_next_app,
    ensure_package_json,
    materialize_site_from_raw,
    parse_files_from_response,
)
from agent.planner import parse_plan


class TestParseFilesFromResponse(unittest.TestCase):
    def test_path_as_fence_label(self):
        raw = """```app/page.tsx
export default function Page() { return null }
```"""
        files = parse_files_from_response(raw)
        self.assertIn("app/page.tsx", files)
        self.assertIn("export default", files["app/page.tsx"])

    def test_tsx_fence_with_backtick_path_above(self):
        raw = """See **`components/Foo.tsx`**

```tsx
export function Foo() { return null }
```"""
        files = parse_files_from_response(raw)
        self.assertIn("components/Foo.tsx", files)

    def test_strips_file_comment_first_line(self):
        raw = """```app/page.tsx
// file: app/page.tsx
const x = 1
```"""
        files = parse_files_from_response(raw)
        self.assertNotIn("// file:", files["app/page.tsx"])

    def test_json_files_key(self):
        raw = json.dumps(
            {"files": {"app/x.tsx": "export default function X(){return null}"}}
        )
        files = parse_files_from_response(raw)
        self.assertIn("app/x.tsx", files)

    def test_raises_when_no_fences(self):
        with self.assertRaises(ValueError):
            parse_files_from_response("just prose, no code")

    def test_json_fence_files_array_manifest(self):
        raw = """```json
{
  "files": [
    {"path": "app/page.tsx", "content": "export default function Page(){return null}"},
    {"path": "app/layout.tsx", "content": "export default function L({ children }: { children: React.ReactNode }) { return children }"}
  ]
}
```"""
        files = parse_files_from_response(raw)
        self.assertIn("app/page.tsx", files)
        self.assertIn("app/layout.tsx", files)

    def test_single_tsx_fence_maps_to_app_page(self):
        raw = """```tsx
export default function Page() { return <main>ok</main> }
```"""
        files = parse_files_from_response(raw)
        self.assertIn("app/page.tsx", files)

    def test_tsx_fence_leading_slash_slash_path(self):
        raw = """```tsx
// app/layout.tsx
import './globals.css'
export default function L({ children }: { children: React.ReactNode }) {
  return <html><body>{children}</body></html>
}
```"""
        files = parse_files_from_response(raw)
        self.assertIn("app/layout.tsx", files)
        self.assertNotIn("// app/layout", files["app/layout.tsx"])
        self.assertIn("import", files["app/layout.tsx"])

    def test_jsx_fence_leading_path(self):
        raw = r"""```jsx
// components/Navbar.jsx
export default function Navbar() { return null }
```"""
        files = parse_files_from_response(raw)
        self.assertIn("components/Navbar.jsx", files)

    def test_markdown_heading_with_backtick_path(self):
        raw = """#### `components/Navbar.tsx`

```tsx
import React from 'react'
export default function Navbar() { return null }
```"""
        files = parse_files_from_response(raw)
        self.assertIn("components/Navbar.tsx", files)

    def test_css_fence_block_comment_path(self):
        raw = """```css
/* app/globals.css */
@tailwind base;
@tailwind components;
```"""
        files = parse_files_from_response(raw)
        self.assertIn("app/globals.css", files)
        self.assertNotIn("/* app/globals.css */", files["app/globals.css"])
        self.assertIn("@tailwind", files["app/globals.css"])

    def test_root_globals_css_moves_to_app(self):
        raw = """```css
/* globals.css */
x { color: red }
```"""
        files = parse_files_from_response(raw)
        from agent.generator import _normalize_loose_paths

        _normalize_loose_paths(files)
        self.assertIn("app/globals.css", files)


class TestEnsureMinimalNextApp(unittest.TestCase):
    def test_empty_dict_adds_layout_and_page(self):
        files: dict[str, str] = {}
        added = ensure_minimal_next_app(files, site_title='Test "Site"')
        self.assertEqual(set(added), {"app/layout.tsx", "app/page.tsx"})
        self.assertIn("app/layout.tsx", files)
        self.assertIn("app/page.tsx", files)
        self.assertIn("globals.css", files["app/layout.tsx"])
        self.assertIn("Test 'Site'", files["app/page.tsx"])

    def test_globals_only_adds_layout_and_page(self):
        files = {"app/globals.css": "@tailwind base;\n"}
        added = ensure_minimal_next_app(files, site_title=None)
        self.assertEqual(set(added), {"app/layout.tsx", "app/page.tsx"})
        self.assertIn("app/layout.tsx", files)

    def test_existing_page_no_stub_for_page(self):
        files = {
            "app/page.tsx": "export default function Page(){return null}",
            "app/globals.css": "x",
        }
        added = ensure_minimal_next_app(files)
        self.assertEqual(added, ["app/layout.tsx"])
        self.assertNotIn("app/page.tsx", added)


class TestMaterializeSiteFromRaw(unittest.TestCase):
    def setUp(self):
        self._td = Path(__file__).resolve().parent / "_gen_test_out"
        if self._td.exists():
            shutil.rmtree(self._td)
        cfg.set_output_dir(self._td)

    def tearDown(self):
        if self._td.exists():
            shutil.rmtree(self._td, ignore_errors=True)

    def test_materialize_writes_expected_paths(self):
        raw = """```app/layout.tsx
import type { ReactNode } from "react"
export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>
}
```
```app/page.tsx
export default function Page() { return <main>ok</main> }
```"""
        result = materialize_site_from_raw(raw, reset_output_dir=True)
        self.assertGreaterEqual(result["files_written"], 5)
        self.assertEqual(result.get("stub_paths"), [])
        self.assertTrue((self._td / "package.json").is_file())
        self.assertTrue((self._td / "app" / "page.tsx").is_file())
        self.assertTrue((self._td / "app" / "layout.tsx").is_file())

    def test_materialize_strips_invalid_page_children_prop(self):
        raw = r"""```tsx
// app/page.tsx
export default function Page({ children }: { children: React.ReactNode }) {
  return <main>{children}</main>
}
```"""
        materialize_site_from_raw(raw, reset_output_dir=True)
        body = (self._td / "app" / "page.tsx").read_text(encoding="utf-8")
        self.assertIn("export default function Page()", body)
        self.assertNotIn("{children}", body)


class TestEnsurePackageJson(unittest.TestCase):
    def test_merges_types_node_when_typescript_present(self):
        files = {
            "package.json": json.dumps({"devDependencies": {"typescript": "^5.6.0"}}),
            "app/page.tsx": "export default function Page() { return null }",
        }
        ensure_package_json(files)
        data = json.loads(files["package.json"])
        self.assertIn("@types/node", data["devDependencies"])


class TestPlannerParsePlan(unittest.TestCase):
    def test_nested_json_inside_fence(self):
        raw = """```json
{
  "site_name": "portfolio",
  "pages": [
    { "name": "Home", "route": "/", "sections": ["Hero", "Projects"] }
  ],
  "components": ["Navbar"],
  "style": { "theme": "dark", "primary_color": "#000" }
}
```"""
        plan = parse_plan(raw)
        self.assertEqual(plan["site_name"], "portfolio")
        self.assertEqual(len(plan["pages"]), 1)


if __name__ == "__main__":
    unittest.main()
