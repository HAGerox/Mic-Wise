import multiprocessing
import uvicorn
import os
import sys

# Add the current directory to sys.path to allow imports from 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.settings import MicWiseSettings

if __name__ == "__main__":
    # Required so the spawned audio engine works inside frozen
    # (PyInstaller-style) Windows executables.
    multiprocessing.freeze_support()
    settings = MicWiseSettings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
