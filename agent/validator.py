"""Build validation: runs npm install + next build and captures errors."""

import subprocess

import agent.config as cfg


def run_install() -> tuple[bool, str]:
    """Run npm install in the output directory.

    Returns (success, output_text).
    """
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(cfg.OUTPUT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
        **cfg.SUBPROCESS_TEXT_KW,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def run_build() -> tuple[bool, str]:
    """Run next build in the output directory.

    Returns (success, output_text).
    """
    result = subprocess.run(
        ["npx", "next", "build"],
        cwd=str(cfg.OUTPUT_DIR),
        capture_output=True,
        text=True,
        timeout=180,
        **cfg.SUBPROCESS_TEXT_KW,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def validate() -> tuple[bool, str]:
    """Run full build pipeline: install → build.

    Returns (success, combined_output).
    """
    ok, install_out = run_install()
    if not ok:
        return False, f"npm install failed:\n{install_out}"

    ok, build_out = run_build()
    if not ok:
        return False, f"next build failed:\n{build_out}"

    return True, "Build succeeded"
