#!/usr/bin/env python3
"""Crawler of Python project, parsing Pypi and cloning their git repo.
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from pystyle import __version__

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line parameters

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
        '--repository',
        help='Crawl a specific repository',
        metavar='https://github.com/julienpalard/pystyle/',
        type=str)
    parser.add_argument(
        '--pypi-project',
        help='Fetch a single PyPI project')
    parser.add_argument(
        'git_store',
        metavar='./git-clones/',
        help='Directory to store git clones.')
    parser.add_argument(
        '--reclone',
        help="Re clone from given pystyle-data to git_store.")
    return parser.parse_args()


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def is_github_project_url(url):
    """Returns True if the URL looks like a github project URL. False
    otherwise.
    """
    return re.match('https://github.com/[^/]+/[^/]+/?', url) is not None


def git_clone_or_update(clone_url, clone_path):
    """Wrapper around git clone / git pull, just try to get an up-to-date
    repo.
    """
    if os.path.isdir(clone_path):
        logger.debug("Git pull on: %s", clone_path)
        try:
            subprocess.run(['git', '-C', clone_path, 'pull', '--ff-only'],
                           check=True)
            return
        except subprocess.CalledProcessError:
            shutil.rmtree(clone_path)
    os.makedirs(clone_path)
    logger.debug("Git clone: %s", clone_url)
    try:
        subprocess.run(['git', 'clone', clone_url, clone_path],
                       stdin=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        logger.error("Clone failed for repo %s", clone_url)
        shutil.rmtree(clone_path, ignore_errors=True)


def clone_repository(github_project_url, clones_path=None, clone_path=None):
    """Clone or update the given github project by URL.
    Give one of clones_path or clone_path:
    - Will clone the project in a directory in clones_path.
    - Or clone the project in clone_path.
    """
    github_project_url = github_project_url.rstrip('/')
    clone_url = github_project_url + '.git'
    if clones_path:
        clone_path = os.path.join(
            clones_path,
            urlparse(github_project_url).path[1:])
    git_clone_or_update(clone_url, clone_path)


def pypi_url_to_github_url(pypi_package_url):
    """By querying the PyPI API, try to find the github page of a pypi project.
    """
    project_response = requests.get(pypi_package_url)
    soup = BeautifulSoup(project_response.content, "html5lib",
                         from_encoding='UTF8')
    for element in soup.select('div.sidebar-section a i.fa-github'):
        github_url = element.parent.get('href')
        if is_github_project_url(github_url):
            return github_url
    return None


def crawl_pypi_project(git_store, pypi_package_url):
    """Crawl a PyPI package by trying to find it upstream git and cloning
    it.
    """
    logger.info("Crawling %s", pypi_package_url)
    github_project_url = pypi_url_to_github_url(pypi_package_url)
    if github_project_url:
        clone_repository(github_project_url, clones_path=git_store)


def crawl_pypi():
    """Crawl PyPI via RSS, return a list of pypi projects.
    """
    updates = feedparser.parse(
        'https://pypi.org/rss/updates.xml')
    packages = feedparser.parse(
        'https://pypi.org/rss/packages.xml')
    return set(package['link'] for package in
               updates['items'] + packages['items'])


def reclone(git_store: str, pystyle_data_path: Union[str, Path]) -> None:
    pystyle_data_path = Path(pystyle_data_path)
    if (pystyle_data_path / Path('github.com')).exists():
        github = pystyle_data_path / Path('github.com')
    else:
        github = pystyle_data_path
    with Pool(processes=4) as pool:
        for org in github.iterdir():
            for project in org.iterdir():
                pool.apply_async(
                    clone_repository,
                    (f"https://github.com/{org.stem}/{project.stem}", ),
                    {'clones_path': git_store})
        pool.close()
        pool.join()


def main():
    """Main entry point allowing external calls
    """
    args = parse_args()
    os.environ['GIT_ASKPASS'] = '/bin/true'
    setup_logging(args.loglevel)
    logger.debug("Starting...")
    if args.repository:
        clone_repository(args.repository, clones_path=args.git_store)
    elif args.pypi_project:
        crawl_pypi_project(args.git_store, args.pypi_project)
    elif args.reclone:
        reclone(args.git_store, args.reclone)
    else:
        pypi_projects = crawl_pypi()
        for pypi_project in pypi_projects:
            crawl_pypi_project(args.git_store, pypi_project)
    logger.debug("Script ends here")


if __name__ == "__main__":
    main()
