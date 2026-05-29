import os
import subprocess
import sys

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
MANAGE_PY = os.path.join(DATA_DIR, '..', 'prj', 'manage.py')

TOTAL_RUNS = 20
LIMIT_PER_RUN = 5000

for i in range(TOTAL_RUNS):
    print(f"\n=== Batch {i + 1}/{TOTAL_RUNS} ===")
    subprocess.run([sys.executable, MANAGE_PY, 'import_movies',
                    '--limit', str(LIMIT_PER_RUN),
                    '--data-dir', DATA_DIR])
