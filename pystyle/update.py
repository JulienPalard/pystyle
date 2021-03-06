#!/usr/bin/env python3

"""Looks for git clones and compute stats about them.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import subprocess
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, TypeVar, Union

import licensename

from pystyle import __version__

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line parameters
    """
    parser = argparse.ArgumentParser(
        description="Crawl github Python repositories and infer their style."
    )
    parser.add_argument(
        "--version", action="version", version="pystyle {ver}".format(ver=__version__)
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        default=0,
        help="Verbose mode (-vv for more, -vvv, …)",
        action="count",
    )
    parser.add_argument(
        "--update",
        help="Do not search for new commits but update an existing stats file",
        action="store_true",
    )
    parser.add_argument("--only", help="Only run updates matching the given pattern")
    parser.add_argument(
        "git_store",
        metavar="../pystyle-clones/",
        help="Directory where git clones are stored.",
    )
    parser.add_argument(
        "stats_csv", metavar="./stats.csv", help="Where to put the stats."
    )
    return parser.parse_args()


def detect_test_engine(repo_path: Path) -> Dict[str, str]:
    """Look for hints about the test engine used by the given repo.
    """
    detected_engines: Counter = Counter()
    files_to_search = [
        "README.txt",
        "README",
        "README.md",
        "README.rst",
        "tox.ini",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements_dev.txt",
        "dev-requirements.txt",
        "requirements-test.txt",
        "test-requirements.txt",
        "test_requirements.txt",
    ]
    known_engines = ["nose", "pytest", "unittest"]
    for file_to_search in files_to_search:
        if (repo_path / file_to_search).exists():
            tox_text = (repo_path / file_to_search).read_text()
            for engine in known_engines:
                if engine in tox_text:
                    detected_engines[engine] += 1
    try:
        return {"test_engine": detected_engines.most_common(1)[0][0]}
    except IndexError:
        return {"test_engine": ""}


def has_typical_dirs(repo_path: Path) -> Dict[str, int]:
    """Given a path to a git clone, returns a dict of present/absent
    directories.
    """
    typical_files = ("doc/", "docs/", "examples/", "src/", "test/", "tests/")
    return {
        "dir:" + typical_dir: int((repo_path / typical_dir).is_dir())
        for typical_dir in typical_files
    }


def has_typical_files(repo_path: Path) -> Dict[str, int]:
    """Given a path to a git clone, returns a dict of present/absent files.
    """
    typical_files = (
        ".gitignore",
        "AUTHORS.md",
        "AUTHORS.rst",
        "CHANGELOG.md",
        "CHANGELOG.rst",
        "CONTRIBUTING.md",
        "CONTRIBUTING.rst",
        "LICENSE",
        "Pipfile",
        "Pipfile.lock",
        "pyproject.toml",
        "LICENSE.txt",
        ".noserc",
        "nose.cfg",
        "Makefile",
        "MANIFEST.in",
        "pytest.ini",
        "README",
        "README.txt",
        "README.md",
        "README.rst",
        "requirements.txt",
        "requirements_dev.txt",
        "setup.cfg",
        "setup.py",
        "test-requirements.txt",
        "tox.ini",
    )
    return {
        "file:" + typical_file: int((repo_path / typical_file).is_file())
        for typical_file in typical_files
    }


def infer_license(repo_path: Path) -> Dict[str, str]:
    """Given a repository path, try to locate the license and infer it.
    """
    probable_license_files = ("LICENSE", "LICENSE.txt", "LICENCE", "LICENCE.txt")
    for probable_license_file in probable_license_files:
        license_path = repo_path / probable_license_file
        try:
            license_name = licensename.from_file(license_path)
            if license_name is not None:
                return {"license": license_name}
            logger.warning("Unknown license for %s", license_path)

        except (FileNotFoundError, UnicodeDecodeError):
            continue
    return {"license": ""}


def count_lines_of_code(path: Path) -> Dict[str, int]:
    """Basic line-of-code counter in a hierarchy.
    """
    interesting_ones = {
        "csv",
        "c",
        "ipynb",
        "json",
        "po",
        "py",
        "xml",
        "yaml",
        "ini",
        "toml",
    }
    source_files = path.rglob("*.*")
    lines_counter: Dict[str, int] = Counter()
    for source_file in source_files:
        if ".git" in source_file.name:
            continue
        try:
            with open(source_file) as opened_file:
                suffix = source_file.suffix[1:].lower()
                if suffix in interesting_ones:
                    lines_counter["lines_of:" + suffix] += len(opened_file.readlines())
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            # Open issue also for symlinks loops?
            pass
    return dict(lines_counter)


def dunder_future(path: Path) -> Dict[str, int]:
    """Search for __future__
    """
    source_files = path.rglob("*.py")
    total_files = 0
    dunder_future_found = 0
    for source_file in source_files:
        try:
            with open(source_file) as opened_file:
                total_files += 1
                if "from __future__ import" in opened_file.read():
                    dunder_future_found += 1
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            # Open issue also for symlinks loops?
            pass
    return {
        "dunder_future_pct": int(
            100 * dunder_future_found / total_files if total_files else 0
        )
    }


def count_shebangs(path: Path) -> Dict[str, int]:
    """Cound number of shebangs encontered in a hierarchy.
    """
    source_files = path.rglob("*.py")
    shebangs: Dict[str, int] = Counter()
    shebangs_qty = 0
    py_files = 0
    for source_file in source_files:
        py_files += 1
        try:
            with open(source_file) as opened_file:
                first_line = opened_file.readline()
            if first_line[0:2] == "#!":
                shebangs_qty += 1
                version = re.search("python[0-9.]*", first_line, re.I)
                if version:
                    shebangs["shebang:" + version.group(0)] += 1
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            pass
    shebangs = dict(shebangs)
    shebangs["shebangs_pct"] = int(100 * (shebangs_qty / py_files if py_files else 0))
    return shebangs


def infer_requirements(path: Path) -> Dict[str, str]:
    """Given the directory of a Python project, try to find its
    requirements.
    """
    import requirements_detector

    try:
        return {
            "requirements": json.dumps(
                [
                    str(requirement)
                    for requirement in requirements_detector.find_requirements(path)
                ]
            )
        }
    except requirements_detector.detect.RequirementsNotFound:
        return {"requirements": "[]"}


def count_pep8_infringement(path: Path) -> int:
    """Invoke pycodestyle on a path just to count number of infrigements.
    """
    pycodestyle_result = subprocess.run(
        ["pycodestyle", "--exclude=.git", "--statistics", "--count", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if not pycodestyle_result.stderr:
        return 0
    try:
        return int(pycodestyle_result.stderr)
    except ValueError:
        # Probably just a warning about pycodestyle itself.
        return 0


IntOrString = TypeVar("IntOrString", int, str, covariant=True)


def infer_style_of_repo(
    path: Path, only: Optional[str] = None
) -> Dict[str, Union[str, int]]:
    """Try to infer some basic properties of a Python project like
    presence or absence of typical files, license, …
    """
    methods: Dict[str, Callable[[Path], Mapping[str, Union[int, str]]]] = {
        "has_file": has_typical_files,
        "has_dir": has_typical_dirs,
        "license": infer_license,
        "detect_test_engine": detect_test_engine,
        # 'lines_of_code': count_lines_of_code,
        # 'pep8_infringement': count_pep8_infringement,
        "shebang": count_shebangs,
        "dunder_future": dunder_future,
        "requirements": infer_requirements,
    }
    result: Dict[str, Union[int, str]] = {}
    try:
        for method_name, method in methods.items():
            if only is None or only in method_name:
                result.update(method(path))
    except Exception:  # pylint: disable=broad-except
        import traceback

        traceback.print_exc()
        logger.exception(f"Unhandled exception while infering style of {path!r}")

    return result


class random_commit:
    """Context manager to temporarily checkout a random commit in an history
    """

    def __init__(self, repo_path: Path) -> None:
        self.initial_commit = None
        self.repo_path = repo_path

    def pick_random_commit(self):
        return random.choice(
            [
                commit
                for commit in subprocess.check_output(
                    ("git", "-C", str(self.repo_path), "rev-list", self.initial_commit),
                    universal_newlines=True,
                ).split("\n")
                if commit
            ]
        )

    def fix_checkout(self):
        status = subprocess.check_output(
            ["git", "-C", str(self.repo_path), "status"], universal_newlines=True
        )
        if b"detached at" not in status:
            return
        logger.info("Trying to fix checkout of %r", self.repo_path)
        branches = subprocess.check_output(["git", "-C", str(self.repo_path), "branch"])
        upstream_branch = [
            branch.strip() for branch in branches.split("\n") if " " not in branch
        ][0]
        subprocess.check_output(
            ["git", "-C", str(self.repo_path), "checkout", "-f", upstream_branch]
        )

    def __enter__(self):
        self.fix_checkout()
        self.initial_commit = subprocess.check_output(
            ("git", "-C", str(self.repo_path), "rev-parse", "HEAD"),
            universal_newlines=True,
        ).rstrip()
        commit = self.pick_random_commit()
        logger.info("Checking out random commit %r", commit)
        subprocess.check_call(
            ("git", "-C", str(self.repo_path), "checkout", "-f", commit),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return commit

    def __exit__(self, *exc):
        logger.info("Checking out back to %r", self.initial_commit)
        subprocess.check_call(
            ("git", "-C", str(self.repo_path), "checkout", "-f", self.initial_commit),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class commit:
    """Context manager to temporarily checkout a given commit.
    """

    def __init__(self, repo_path: Path, commit: str) -> None:
        self.initial_commit = None
        self.target_commit = commit
        self.repo_path = repo_path

    def __enter__(self):
        self.initial_commit = subprocess.check_output(
            ("git", "-C", str(self.repo_path), "rev-parse", "HEAD"),
            universal_newlines=True,
        ).rstrip()
        logger.info("Checking out random commit %r", self.target_commit)
        subprocess.check_call(
            ("git", "-C", str(self.repo_path), "checkout", "-f", self.target_commit),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return commit

    def __exit__(self, *exc):
        logger.info("Checking out back to %r", self.initial_commit)
        subprocess.check_call(
            ("git", "-C", str(self.repo_path), "checkout", "-f", self.initial_commit),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def infer_style(repo: Path, only: str = None) -> Optional[Dict[str, Union[str, int]]]:
    logger.info("Working on repo %r", repo)
    with random_commit(repo) as commit:
        commit_date = subprocess.check_output(
            ("git", "-C", str(repo), "show", "--pretty=format:%cI", "-s"),
            universal_newlines=True,
        )
        style = infer_style_of_repo(repo, only)
        style.update({"commit": commit, "repo": str(repo), "date": commit_date})
        return style


def update_style(git_store: Path, only: str, line: dict):
    repo = git_store / line["repo"]
    with commit(repo, line["commit"]):
        line.update(infer_style_of_repo(repo, only))
        return line


def update_style_of_all_repos(
    git_store: Path, stats_csv: Path, only: str = None
) -> None:
    """Recompute the stats of an existing stats file.
    """
    with open(stats_csv, "r", newline="\n") as csv_file, Pool(processes=4) as pool:
        reader = csv.DictReader(csv_file, dialect=csv.unix_dialect)
        all_styles = pool.starmap(
            update_style, ((git_store, only, line) for line in reader)
        )
        fieldnames = reader.fieldnames
    all_styles = [style for style in all_styles if style is not None]
    with open(
        str(stats_csv).replace(".csv", "-new.csv"), "w", newline="\n"
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fieldnames, dialect=csv.unix_dialect
        )
        writer.writeheader()
        writer.writerows(all_styles)


def infer_style_of_all_repos(
    git_store: Path, stats_csv: Path, only: str = None
) -> None:
    """Compute stats file from a bunch of clones.
    """
    with Pool(processes=8) as pool:
        all_styles = pool.starmap(
            infer_style, [(path, only) for path in git_store.glob("*/*/*/")]
        )
    all_styles = [style for style in all_styles if style is not None]
    for style in all_styles:
        style["repo"] = Path(style["repo"]).relative_to(git_store)
    headers = {key for style in all_styles for key in set(style)}
    with open(stats_csv, "w") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=list(headers), dialect=csv.unix_dialect
        )
        writer.writeheader()
        writer.writerows(all_styles)


def main() -> None:
    """Main entry point allowing external calls
    """
    args = parse_args()
    os.environ["GIT_ASKPASS"] = "/bin/true"
    logging.basicConfig(
        level=50 - (args.loglevel * 10),
        stream=sys.stdout,
        format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if not args.update:
        infer_style_of_all_repos(Path(args.git_store), Path(args.stats_csv), args.only)
    else:
        update_style_of_all_repos(Path(args.git_store), Path(args.stats_csv), args.only)


if __name__ == "__main__":
    main()
