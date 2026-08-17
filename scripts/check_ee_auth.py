"""Connectivity check: confirm Earth Engine credentials work.

Run this once after ``ee.Authenticate()`` to verify the configured Cloud project
is reachable. Authentication is interactive (it opens a browser), so it is kept
behind ``main()`` and never triggered on import.
"""

import ee

from src.config import EE_PROJECT


def main() -> None:
    ee.Initialize(project=EE_PROJECT)
    # Round-trip a trivial computation to prove the connection really works.
    print(f"Earth Engine initialized correctly (project: {EE_PROJECT})")
    print(f"Server round-trip: {ee.Number(1).add(1).getInfo()}")


if __name__ == "__main__":
    main()
