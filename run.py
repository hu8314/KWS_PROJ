import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from main import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8023)