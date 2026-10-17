"""gitweave CLI entry point — full verb dispatch."""

import argparse
import json
import os
import sys

from gitweave.plan import plan
from gitweave.apply import apply
from gitweave.reset import reset
from gitweave.auth import get_github_client, get_caller_token, resolve_caller_login, get_installation_token
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
        if getattr(args, "json", False):
            print(result.to_json())
        else:
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
    """Return (gh_org, policy, caller_login) or raise CallerTokenRequiredError/PolicyError.

    Policy is loaded before GitHub auth so a missing/invalid config/policy.yaml
    produces an immediate, clear error rather than an auth failure.
    """
    policy = PolicyLoader().load()
    token = get_caller_token()
    gh = get_github_client()
    caller_login = resolve_caller_login(token)
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
        result = self_serve_list_exceptions(args.team, args.repo, policy, gh_org)
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except PolicyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_overlay_apply(args):
    from gitweave.managers.overlays import apply_overlays_for_repo, BranchProtectedError
    try:
        gh_org = _get_org_client()
        results = apply_overlays_for_repo(args.repo, gh_org)
        for r in results:
            print(f"  {r.action}: {r.repo} — {r.message}")
        sys.exit(0)
    except BranchProtectedError as e:
        print(
            f"Error: {e.repo} branch '{e.branch}' is protected: {e.protection}",
            file=sys.stderr,
        )
        sys.exit(1)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_overlay_status(args):
    from gitweave.managers.overlays import get_overlay_status
    try:
        gh_org = _get_org_client()
        gh_repo = gh_org.get_repo(args.repo)
        modules = get_overlay_status(gh_repo)
        if not modules:
            print("No modules applied.")
        else:
            for m in modules:
                print(f"  {m['name']} @ {m['version']}")
                for k, v in (m.get("inputs") or {}).items():
                    print(f"    {k}: {v}")
        sys.exit(0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_overlay_request(args):
    from gitweave.self_serve.overlay_request import (
        self_serve_overlay_request,
        OverlayRequestDenied,
    )
    from gitweave.policy import PolicyError
    from gitweave.transport import RecordingTransport
    import requests as _req

    def _live_handler(method, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {get_installation_token()}"
        resp = _req.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 404:
            return None  # resource not found is valid (e.g. .copier-answers.yml absent)
        resp.raise_for_status()
        return resp.json()

    transport = RecordingTransport(handler=_live_handler)

    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_overlay_request(
            args.team, args.repo, args.module, gh_org, policy, caller_login,
            transport=transport,
        )
        import json
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except (PolicyError, OverlayRequestDenied) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_module_render(args):
    from gitweave.module_render import render_module, CopierVersionError
    data = {}
    for pair in (args.data or []):
        k, _, v = pair.partition("=")
        data[k.strip()] = v.strip()
    try:
        render_module(args.name, args.dest, data=data)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except CopierVersionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the gw argument parser without consuming argv.

    Extracted from main() so tests can walk the parser tree to enumerate
    registered subcommands and verify permission-check coverage.
    """
    parser = argparse.ArgumentParser(prog="gw", description="GitWeave org controller")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Diff declaration against org state")
    p_plan.add_argument("--fixture", metavar="PATH")
    p_plan.add_argument("--json", action="store_true")
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
    p_le.add_argument("--team", metavar="TEAM")  # optional: omit to list all teams
    p_le.add_argument("--repo", required=True, metavar="REPO")
    p_le.set_defaults(func=cmd_self_serve_list_exceptions)

    # module subcommands
    p_mod = sub.add_parser("module", help="Copier module operations")
    mod_sub = p_mod.add_subparsers(dest="mod_command", required=True)

    p_mr = mod_sub.add_parser("render", help="Render a module offline to a destination")
    p_mr.add_argument("name", metavar="NAME", help="Module name (snake_case)")
    p_mr.add_argument("--dest", required=True, metavar="DIR", help="Destination directory")
    p_mr.add_argument(
        "--data",
        metavar="KEY=VALUE",
        nargs="*",
        default=[],
        help="Override copier question answers (key=value pairs)",
    )
    p_mr.set_defaults(func=cmd_module_render)

    # overlay subcommands
    p_ov = sub.add_parser("overlay", help="Module overlay operations")
    ov_sub = p_ov.add_subparsers(dest="ov_command", required=True)

    p_oa = ov_sub.add_parser("apply", help="Apply declared overlays for a repo")
    p_oa.add_argument("repo", metavar="REPO", help="Repository name")
    p_oa.set_defaults(func=cmd_overlay_apply)

    p_os = ov_sub.add_parser("status", help="Show applied overlay modules for a repo")
    p_os.add_argument("repo", metavar="REPO", help="Repository name")
    p_os.set_defaults(func=cmd_overlay_status)

    p_or = ov_sub.add_parser("request", help="Request a module for a team repo")
    p_or.add_argument("--team", required=True, metavar="SLUG")
    p_or.add_argument("--repo", required=True, metavar="REPO")
    p_or.add_argument("--module", required=True, metavar="NAME")
    p_or.set_defaults(func=cmd_overlay_request)

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
