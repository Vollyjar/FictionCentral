"""
FictionCentral — Entry Point
"""
import logging
import sys
import os

# Ensure the project root is on sys.path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import init_db  # noqa: E402
from scraper.engine import DownloadEngine  # noqa: E402
from gui.app import App  # noqa: E402


def main() -> None:
    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("fiction_central")
    logger.info("Starting FictionCentral…")

    # Database
    init_db()
    logger.info("Database initialised")

    # Download engine
    engine = DownloadEngine()

    # GUI
    app = App(download_engine=engine)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
