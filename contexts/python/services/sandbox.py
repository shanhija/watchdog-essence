"""Sandbox — an isolated copy of the app where a fix can be drafted and tested
without touching your working tree. Here it's a temp directory + a subprocess;
swap for a container/VM (ESSENCE §4E). The non-negotiable is pristine + isolated."""
import difflib
import os
import shutil
import subprocess
import tempfile


class LocalSandbox:
    def __init__(self, src_root: str) -> None:
        self.src_root = src_root
        self.dir = tempfile.mkdtemp(prefix="watchdog-sandbox-")
        shutil.copytree(os.path.join(src_root, "app"), os.path.join(self.dir, "app"))
        self._orig: dict[str, str] = {}

    def write_files(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            p = os.path.join(self.dir, rel)
            if rel not in self._orig:
                self._orig[rel] = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)

    def run_tests(self) -> tuple[bool, str]:
        env = dict(os.environ, APP_LOG=os.path.join(self.dir, "sandbox.log"))
        proc = subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "app/tests", "-t", "."],
            cwd=self.dir, env=env, capture_output=True, text=True,
        )
        return proc.returncode == 0, proc.stdout + proc.stderr

    def diff(self) -> str:
        chunks = []
        for rel, orig in self._orig.items():
            new = open(os.path.join(self.dir, rel), encoding="utf-8").read()
            if new == orig:
                continue
            chunks.append("".join(difflib.unified_diff(
                orig.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=f"a/{rel}", tofile=f"b/{rel}",
            )))
        return "".join(chunks)

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
