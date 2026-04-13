"""Unit tests for agent.generator (parse + materialize)."""

import json
import shutil
import unittest
from pathlib import Path

import agent.config as cfg
from agent.generator import materialize_site_from_raw, parse_files_from_response


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
        self.assertTrue((self._td / "package.json").is_file())
        self.assertTrue((self._td / "app" / "page.tsx").is_file())
        self.assertTrue((self._td / "app" / "layout.tsx").is_file())


if __name__ == "__main__":
    unittest.main()
