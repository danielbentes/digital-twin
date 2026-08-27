#!/usr/bin/env python3
"""Compatibility entry point for the synthesize package."""

from synthesize import *  # noqa: F403
from synthesize import __all__ as __all__, main as main


if __name__ == "__main__":
    raise SystemExit(main())
