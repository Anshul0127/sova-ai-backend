#!/usr/bin/env python3
import os
import sys

if __name__ == "__main__":
    # Change to backend directory so relative imports work
    backend_dir = os.path.dirname(__file__)
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)
    
    import uvicorn
    from main import app
    uvicorn.run(app, host="0.0.0.0", port=8000)