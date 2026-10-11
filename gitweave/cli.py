"""gitweave CLI entry point — full verb dispatch."""

import argparse
import json
import os
import sys

from gitweave.plan import plan
from gitweave.apply import apply
from gitweave.reset import reset
from gitweave.auth import get_github_client


def _get_org_client():
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def cmd_plan(args):
    try:
        result = plan(fixture_path=getattr(args, "fixture", None))
        result.print()
        sys.exit(0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_apply(args):
    try:
        gh_org = _get_org_client()
        result = apply(gh_org, json_mode=args.json)
        if args.json:
            print(result.to_json())
        else:
            for s in result.statuses:
                print(
                    f"  {'ok' if s.status == 'ok' else 'ERROR'}: {s.name}"
                    + (f" — {s.error}" if s.error else "")
                )
        sys.exit(1 if result.has_errors else 0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_reset(args):
    try:
        gh_org = _get_org_client()
        result = reset(gh_org)
        if result.nothing_changed:
            print("Nothing changed.")
        else:
            for s in result.statuses:
                print(f"  {'ok' if s.status == 'ok' else 'ERROR'}: {s.name}")
        sys.exit(1 if any(s.status == "error" for s in result.statuses) else 0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_org_show(args):
    gh_org = _get_org_client()
    from gitweave.managers.org import OrgSettingsManager
    print(json.dumps(OrgSettingsManager(gh_org).current(), indent=2))


def cmd_org_repos(args):
    from gitweave.managers.repos import ReposManager
    print(
        json.dumps(
            [{"name": r.name} for r in ReposManager(_get_org_client()).list_managed()],
            indent=2,
        )
    )


def cmd_org_teams(args):
    from gitweave.managers.teams import TeamsManager
    print(
        json.dumps(
            [{"name": t.name} for t in TeamsManager(_get_org_client()).list_managed()],
            indent=2,
        )
    )


def cmd_org_rulesets(args):
    from gitweave.managers.rulesets import RulesetsManager
    print(json.dumps(RulesetsManager(_get_org_client()).list_managed(), indent=2))


def main():
    parser = argparse.ArgumentParser(prog="gw", description="GitWeave org controller")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Diff declaration against org state")
    p_plan.add_argument("--fixture", metavar="PATH")
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="Apply declaration to live org")
    p_apply.add_argument("--json", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    p_reset = sub.add_parser("reset", help="Delete prefixed resources + restore defaults")
    p_reset.set_defaults(func=cmd_reset)

    p_org = sub.add_parser("org", help="Read-back org state")
    org_sub = p_org.add_subparsers(dest="org_command", required=True)
    for name, fn in [
        ("show", cmd_org_show),
        ("repos", cmd_org_repos),
        ("teams", cmd_org_teams),
        ("rulesets", cmd_org_rulesets),
    ]:
        p = org_sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
