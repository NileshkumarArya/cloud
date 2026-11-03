#!/usr/bin/env python3
"""Convenience launcher for the CWMS command-line simulator."""
from cwms_simulator.cli import create_parser, main

if __name__ == "__main__":
    raise SystemExit(main(create_parser().parse_args()))
