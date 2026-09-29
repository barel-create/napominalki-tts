"""
Entry point. This exact file is what PyInstaller packages into the .exe,
and it's also what you run directly with `python run.py` from source.

Launches the GUI (gui.py) -- the old console loop (main.py) is kept in the
tree for reference/debugging but is no longer what ships.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from tts_client.gui import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
