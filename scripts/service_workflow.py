"""Launch configured service orchestration using existing local dependencies."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {**os.environ, 'DS_USAGE_ENGINE':'dsorchestrator', 'DS_USAGE_PROCESS':'service-workflow'}
    env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT / 'instrumentation'), str(ROOT / '.domain_deps'), env.get('PYTHONPATH', ''))))
    return subprocess.run([sys.executable, 'main.py', *sys.argv[1:]], cwd=ROOT.parent / 'dsorchestrator', env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
