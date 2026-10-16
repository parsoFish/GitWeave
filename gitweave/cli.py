"""gitweave CLI entry point — full verb dispatch."""

import argparse
import json
import os
import sys

from gitweave.plan import plan
from gitweave.apply import apply
from gitweave.reset import reset
from gitweave.auth import get_github_client, get_caller_token, resolve_caller_login
from gitweave.auth import CallerTokenRequiredError
from gitweave.policy import PolicyLoader, PolicyDenied, PolicyError
from gitweave.self_serve.new_repo import self_serve_new_repo
from gitweave.self_serve.update_content import self_serve_update_content
from gitweave.self_serve.membership import self_serve_add_member, self_serve_remove_member
from gitweave.self_serve.exceptions import self_serve_add_exception, self_serve_list_exceptions


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


def _self_serve_auth():
    """Return (gh_org, policy, caller_login) or raise CallerTokenRequiredError."""
    token = get_caller_token()
    gh = get_github_client()
    caller_login = resolve_caller_login(token)
    policy = PolicyLoader().load()
    gh_org = gh.get_organization(os.environ["GW_ORG"])
    return gh_org, policy, caller_login


def cmd_self_serve_new_repo(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_new_repo(args.team, args.name, gh_org, policy, caller_login)
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_self_serve_update_content(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        value = args.value.split(",") if args.setting == "topics" else args.value
        result = self_serve_update_content(
            args.team, args.repo, args.setting, value, gh_org, policy, caller_login
        )
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_self_serve_add_member(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_add_member(args.team, args.member, gh_org, policy, caller_login)
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_self_serve_remove_member(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_remove_member(args.team, args.member, gh_org, policy, caller_login)
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_self_serve_add_exception(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_add_exception(
            args.team, args.repo, args.exception, args.reason, gh_org, policy, caller_login
        )
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_self_serve_list_exceptions(args):
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_list_exceptions(args.repo, gh_org)
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


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

    # self-serve subcommands
    p_ss = sub.add_parser("self-serve", help="Team self-service operations")
    ss_sub = p_ss.add_subparsers(dest="ss_command", required=True)

    p_nr = ss_sub.add_parser("new-repo", help="Create a new repo for a team")
    p_nr.add_argument("--team", required=True, metavar="SLUG")
    p_nr.add_argument("--name", required=True, metavar="NAME")
    p_nr.set_defaults(func=cmd_self_serve_new_repo)

    p_uc = ss_sub.add_parser("update-content", help="Update repo content settings")
    p_uc.add_argument("--team", required=True, metavar="SLUG")
    p_uc.add_argument("--repo", required=True, metavar="REPO")
    p_uc.add_argument("--setting", required=True, metavar="TYPE")
    p_uc.add_argument("--value", required=True, metavar="VALUE")
    p_uc.set_defaults(func=cmd_self_serve_update_content)

    p_am = ss_sub.add_parser("add-member", help="Add a member to a team")
    p_am.add_argument("--team", required=True, metavar="SLUG")
    p_am.add_argument("--member", required=True, metavar="LOGIN")
    p_am.set_defaults(func=cmd_self_serve_add_member)

    p_rm = ss_sub.add_parser("remove-member", help="Remove a member from a team")
    p_rm.add_argument("--team", required=True, metavar="SLUG")
    p_rm.add_argument("--member", required=True, metavar="LOGIN")
    p_rm.set_defaults(func=cmd_self_serve_remove_member)

    p_ae = ss_sub.add_parser("add-exception", help="Record a policy exception on a repo")
    p_ae.add_argument("--team", required=True, metavar="SLUG")
    p_ae.add_argument("--repo", required=True, metavar="REPO")
    p_ae.add_argument("--exception", required=True, metavar="KEY")
    p_ae.add_argument("--reason", required=True, metavar="TEXT")
    p_ae.set_defaults(func=cmd_self_serve_add_exception)

    p_le = ss_sub.add_parser("list-exceptions", help="List policy exceptions for a repo")
    p_le.add_argument("--repo", required=True, metavar="REPO")
    p_le.set_defaults(func=cmd_self_serve_list_exceptions)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
