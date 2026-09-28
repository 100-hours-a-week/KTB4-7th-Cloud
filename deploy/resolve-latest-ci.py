#!/usr/bin/env python3
"""Resolve the latest successful dev push CI for a deployment target."""

import json
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WORKFLOWS = {
    "backend": ("KTB4-7th-BE", "ci.yml"),
    "ai": ("KTB4-7th-AI", "ci.yml"),
    "frontend": ("KTB4-7th-FE", "pr-ci.yml"),
}


def github_json(path):
    request = Request(
        f"https://api.github.com/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "memme-cloud-deploy",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def resolve(service, fetch=github_json):
    repository, workflow = WORKFLOWS[service]
    base = f"repos/100-hours-a-week/{repository}"
    branch = fetch(f"{base}/branches/dev")
    sha = branch["commit"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("dev branch did not return a full commit SHA")

    query = urlencode({"branch": "dev", "event": "push", "head_sha": sha, "per_page": 1})
    runs = fetch(f"{base}/actions/workflows/{workflow}/runs?{query}")["workflow_runs"]
    if (
        not runs
        or runs[0]["head_sha"] != sha
        or runs[0]["head_branch"] != "dev"
        or runs[0]["event"] != "push"
        or runs[0]["conclusion"] != "success"
    ):
        raise ValueError(f"Latest dev commit {sha} has no successful push CI; wait for CI or fix it")

    return sha, runs[0]["html_url"]


if __name__ == "__main__":
    try:
        commit_sha, ci_run_url = resolve(sys.argv[1])
    except (IndexError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"commit_sha={commit_sha}")
    print(f"ci_run_url={ci_run_url}")
