"""gitweave CLI entry point."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gw",
        description="gitweave — Git repository overlay management",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # plan
    subparsers.add_parser("plan", help="Show pending changes")

    # apply
    subparsers.add_parser("apply", help="Apply overlay changes")

    # reset
    subparsers.add_parser("reset", help="Reset overlay to base state")

    # org
    org_parser = subparsers.add_parser("org", help="Manage GitHub organisation settings")
    org_sub = org_parser.add_subparsers(dest="org_command", metavar="ORG_COMMAND")
    org_sub.add_parser("show", help="Show org configuration")
    org_sub.add_parser("repos", help="List managed repositories")
    org_sub.add_parser("teams", help="List managed teams")
    org_sub.add_parser("rulesets", help="List managed rulesets")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    raise NotImplementedError(f"{args.command!r} not yet implemented")


if __name__ == "__main__":
    main()
