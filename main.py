"""AICFA worker entry point.

This minimal process keeps the Freim/Frostdeploy Python worker alive
while Phase 1 data infrastructure is being built.
"""

import time


def main() -> None:
    print("AICFA worker started.", flush=True)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
