"""Run whole-interaction frame checks through the shared production pipeline fixture."""
from pathlib import Path
import runpy
import sys

sys.argv[1:1] = ['--frame-startup']
runpy.run_path(str(Path(__file__).with_name('check_quick_transfer_pipeline.py')), run_name='__main__')
