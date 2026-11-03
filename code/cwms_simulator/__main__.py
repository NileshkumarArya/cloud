"""Allow `python -m cwms_simulator` to run the CLI."""
from .cli import main, create_parser

if __name__ == "__main__":
    raise SystemExit(main(create_parser().parse_args()))