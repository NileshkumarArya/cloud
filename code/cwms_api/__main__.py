"""Allow `python -m cwms_api` to start the API server."""
from .main import run_server

if __name__ == "__main__":
    run_server()