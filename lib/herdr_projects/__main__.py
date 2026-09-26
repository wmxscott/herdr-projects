import sys
from pathlib import Path

# bin/herdr-projects runs this file with `python -I`, which leaves lib/ off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_projects.cli import main

sys.exit(main())
