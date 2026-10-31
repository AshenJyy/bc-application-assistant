"""Plugin-relative entry point; no installation of the project is required."""
from bc_application.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
