import os
import subprocess
import sys

MANAGE_PY = os.path.join(os.path.dirname(__file__), '..', 'prj', 'manage.py')

TOTAL_RUNS = 100
LIMIT_PER_RUN = 500

for i in range(TOTAL_RUNS):
    print(f"\n=== Batch {i + 1}/{TOTAL_RUNS} ===")
    subprocess.run([sys.executable, MANAGE_PY, 'import_movies', '--limit', str(LIMIT_PER_RUN)])
