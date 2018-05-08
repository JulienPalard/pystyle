#!/usr/bin/env python3

"""Looks for git clones and compute stats about them.
"""

import os
import sys
import glob
import json
import logging
import argparse
from collections import Counter

from pystyle import __version__
import licensename


logger = logging.getLogger(__name__)


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
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
        metavar='./git-clones/',
        help='Directory where git clones are stored.')
    parser.add_argument(
        'json_store',
        help='Where to put the style files.')
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def has_typical_dirs(repo_path):
    """Given a path to a git clone, returns a dict of present/absent
    directories.
    """
    typical_files = ('doc/',
                     'docs/',
                     'examples/',
                     'src/',
                     'test/',
                     'tests/')
    return {typical_dir: os.path.isdir(os.path.join(repo_path, typical_dir))
            for typical_dir in typical_files}


def has_typical_files(repo_path):
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
    return {typical_file: os.path.isfile(os.path.join(repo_path, typical_file))
            for typical_file in typical_files}


def infer_license(repo_path):
    """Given a repository path, try to locate the license and infer it.
    """
    probable_license_files = ('LICENSE', 'LICENSE.txt',
                              'LICENCE', 'LICENCE.txt')
    for probable_license_file in probable_license_files:
        license_path = os.path.join(repo_path, probable_license_file)
        try:
            license_name = licensename.from_file(license_path)
            if license_name is not None:
                return license_name
            else:
                logger.warning("Unknown license for %s", license_path)

        except (FileNotFoundError, UnicodeDecodeError):
            continue
    return None


def count_lines_of_code(path):
    """Basic line-of-code counter in a hierarchy.
    """
    source_files = glob.glob(os.path.join(path, '**', '*.*'), recursive=True)
    lines_counter = Counter()
    for source_file in source_files:
        if '.git' in source_file:
            continue
        try:
            with open(source_file) as opened_file:
                lines_counter[source_file.split('.')[-1]] += len(
                    opened_file.readlines())
        except (UnicodeDecodeError, IsADirectoryError,
                FileNotFoundError, OSError):
            # We may open issues for broken symlinks þ
            # Open issue also for symlinks loops?
            pass
    return dict(lines_counter)


def count_shebangs(path):
    """Cound number of shebangs encontered in a hierarchy.
    """
    source_files = glob.glob(os.path.join(path, '**', '*.py'), recursive=True)
    shebang_counter = Counter()
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


def infer_requirements(path):
    """Given the directory of a Python project, try to find its
    requirements.
    """
    import requirements_detector
    try:
        return [str(requirement) for requirement in
                requirements_detector.find_requirements(path)]
    except requirements_detector.detect.RequirementsNotFound:
        return []


def count_pep8_infringement(path):
    """Invoke pycodestyle on a path just to count number of infrigements.
    """
    import subprocess
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


def infer_style_of_repo(path, only=None):
    """Try to infer some basic properties of a Python project like
    presence or absence of typical files, license, …
    """
    methods = {'has_file': has_typical_files,
               'has_dir': has_typical_dirs,
               'license': infer_license,
               'lines_of_code': count_lines_of_code,
               'pep8_infringement': count_pep8_infringement,
               'shebang': count_shebangs,
               'requirements': infer_requirements}
    return {key: method(path) for key, method in methods.items() if
            only is None or only in key}


def infer_style(git_store, json_store, only=None):
    """Compute stats file from a bunch of clones.
    """
    for path in glob.glob(git_store + '/*/*/'):
        style_json_path = os.path.join(json_store,
                                       *path.split('/')[-3:-1],
                                       'style.json')
        if not os.path.exists(style_json_path) and only is not None:
            continue  # Do not create partial json files.
        os.makedirs(os.path.dirname(style_json_path), exist_ok=True)
        style = infer_style_of_repo(path, only)
        if os.path.exists(style_json_path):
            try:
                with open(style_json_path, 'r') as json_stats:
                    old_style = json.load(json_stats)
                old_style.update(style)
                style = old_style
            except json.decoder.JSONDecodeError:
                print("Malformed json in {}".format(style_json_path))
        with open(style_json_path, 'w') as json_stats:
            json.dump(style, json_stats, indent=4, sort_keys=True)


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    os.environ['GIT_ASKPASS'] = '/bin/true'
    setup_logging(args.loglevel)
    infer_style(args.git_store, args.json_store, args.only)


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
