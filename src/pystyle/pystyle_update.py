#!/usr/bin/env python3

"""Looks for git clones and compute stats about them.
"""

import argparse
import glob
import json
import logging
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import licensename

from pystyle import __version__

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line parameters
    """
    parser = argparse.ArgumentParser(
        description="Crawl github Python repositories and infer their style.")
    parser.add_argument(
        '--version',
        action='version',
        version='pystyle {ver}'.format(ver=__version__))
    parser.add_argument(
        '-v',
        '--verbose',
        dest="loglevel",
        help="set loglevel to INFO",
        action='store_const',
        const=logging.INFO)
    parser.add_argument(
        '-vv',
        '--very-verbose',
        dest="loglevel",
        help="set loglevel to DEBUG",
        action='store_const',
        const=logging.DEBUG)
    parser.add_argument(
        '--only',
        help="Only run updates matching the given pattern")
    parser.add_argument(
        'git_store',
        metavar='../pystyle-clones/',
        help='Directory where git clones are stored.')
    parser.add_argument(
        'json_store',
        metavar='../pystyle-data/github.com/',
        help='Where to put the style files.')
    return parser.parse_args()


def setup_logging(loglevel: int) -> None:
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def has_typical_dirs(repo_path: Path) -> Dict[str, bool]:
    """Given a path to a git clone, returns a dict of present/absent
    directories.
    """
    typical_files = ('doc/',
                     'docs/',
                     'examples/',
                     'src/',
                     'test/',
                     'tests/')
    return {typical_dir: (repo_path / typical_dir).is_dir()
            for typical_dir in typical_files}


def has_typical_files(repo_path: Path) -> Dict[str, bool]:
    """Given a path to a git clone, returns a dict of present/absent files.
    """
    typical_files = ('.gitignore',
                     'AUTHORS.md',
                     'AUTHORS.rst',
                     'CHANGELOG.md',
                     'CHANGELOG.rst',
                     'CONTRIBUTING.md',
                     'CONTRIBUTING.rst',
                     'LICENSE',
                     'LICENSE.txt',
                     'MANIFEST.in',
                     'pytest.ini',
                     'README',
                     'README.md',
                     'README.rst',
                     'requirements.txt',
                     'setup.cfg',
                     'setup.py',
                     'test-requirements.txt',
                     'tox.ini',
                     'Makefile')
    return {typical_file: (repo_path / typical_file).is_file()
            for typical_file in typical_files}


def infer_license(repo_path: Path) -> Optional[str]:
    """Given a repository path, try to locate the license and infer it.
    """
    probable_license_files = ('LICENSE', 'LICENSE.txt',
                              'LICENCE', 'LICENCE.txt')
    for probable_license_file in probable_license_files:
        license_path = repo_path / probable_license_file
        try:
            license_name = licensename.from_file(license_path)
            if license_name is not None:
                return license_name
            else:
                logger.warning("Unknown license for %s", license_path)

        except (FileNotFoundError, UnicodeDecodeError):
            continue
    return None


def count_lines_of_code(path: Path) -> Dict[str, int]:
    """Basic line-of-code counter in a hierarchy.
    """
    source_files = path.rglob('*.*')
    lines_counter: Dict[str, int] = Counter()
    for source_file in source_files:
        if '.git' in source_file.name:
            continue
        try:
            with open(source_file) as opened_file:
                lines_counter[source_file.suffix[1:]] += len(
                    opened_file.readlines())
        except (UnicodeDecodeError, IsADirectoryError,
                FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            # Open issue also for symlinks loops?
            pass
    return dict(lines_counter)


def count_shebangs(path: Path) -> Dict[str, int]:
    """Cound number of shebangs encontered in a hierarchy.
    """
    source_files = path.rglob('*.py')
    shebang_counter: Dict[str, int] = Counter()
    for source_file in source_files:
        try:
            with open(source_file) as opened_file:
                first_line = opened_file.readline()
            if '#!' in first_line:
                shebang_counter[first_line[:-1]] += 1
        except (UnicodeDecodeError, IsADirectoryError,
                FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            pass
    return dict(shebang_counter)


def infer_requirements(path: Path) -> List[str]:
    """Given the directory of a Python project, try to find its
    requirements.
    """
    import requirements_detector
    try:
        return [str(requirement) for requirement in
                requirements_detector.find_requirements(path)]
    except requirements_detector.detect.RequirementsNotFound:
        return []


def count_pep8_infringement(path: Path) -> int:
    """Invoke pycodestyle on a path just to count number of infrigements.
    """
    pycodestyle_result = subprocess.run(
        ['pycodestyle', '--exclude=.git', '--statistics', '--count', path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True)
    if not pycodestyle_result.stderr:
        return 0
    try:
        return int(pycodestyle_result.stderr)
    except ValueError:
        # Probably just a warning about pycodestyle itself.
        return 0


def infer_style_of_repo(path: Path, only: Optional[str] = None) -> Dict[
        str, Union[str, int]]:
    """Try to infer some basic properties of a Python project like
    presence or absence of typical files, license, …
    """
    methods: Dict[str, Callable[[Path], Any]] = {
        'has_file': has_typical_files,
        'has_dir': has_typical_dirs,
        'license': infer_license,
        'lines_of_code': count_lines_of_code,
        'pep8_infringement': count_pep8_infringement,
        'shebang': count_shebangs,
        'requirements': infer_requirements}
    return {key: method(path) for key, method in methods.items() if
            only is None or only in key}


class random_commit:
    def __init__(self, repo_path: Path) -> None:
        self.initial_commit = None
        self.repo_path = repo_path

    def pick_random_commit(self):
        return random.choice(
            [commit for commit in
             subprocess.check_output(
                 ('git', '-C', str(self.repo_path),
                  'rev-list', self.initial_commit),
                 universal_newlines=True).split('\n') if commit])

    def __enter__(self):
        self.initial_commit = subprocess.check_output(
            ('git', '-C', str(self.repo_path), 'rev-parse', 'HEAD'),
            universal_newlines=True).rstrip()
        subprocess.check_call(('git', '-C', str(self.repo_path), 'checkout',
                               self.pick_random_commit()))

    def __exit__(self, *exc):
        subprocess.check_call(('git', '-C', str(self.repo_path), 'checkout',
                               self.initial_commit))


def infer_style(git_store: Path, json_store: Path, only: str = None) -> None:
    """Compute stats file from a bunch of clones.
    """
    for path in git_store.glob('*/*/'):
        with random_commit(path):
            commit_date = subprocess.check_output(
                ('git', '-C', str(path), 'show', '--pretty=format:%cI', '-s'),
                universal_newlines=True)
            style_json_path = (json_store / path.parts[-2] / path.parts[-1] /
                               (commit_date + '.json'))
            style_json_path.parent.mkdir(parents=True, exist_ok=True)
            style = infer_style_of_repo(path, only)
            if style_json_path.exists():
                try:
                    with open(style_json_path, 'r') as json_stats:
                        old_style = json.load(json_stats)
                    old_style.update(style)
                    style = old_style
                except json.decoder.JSONDecodeError:
                    logger.warning("Malformed json in %s", style_json_path)
            with open(style_json_path, 'w') as json_stats:
                json.dump(style, json_stats, indent=4, sort_keys=True)


def main() -> None:
    """Main entry point allowing external calls
    """
    args = parse_args()
    os.environ['GIT_ASKPASS'] = '/bin/true'
    setup_logging(args.loglevel)
    infer_style(Path(args.git_store), Path(args.json_store), args.only)


if __name__ == "__main__":
    main()
