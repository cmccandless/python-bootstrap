#!/usr/bin/env python
import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime

import requests

try:
    from itertools import izip_longest
    zip_longest = izip_longest
except ImportError:
    from itertools import zip_longest
try:
    user_input = raw_input
except NameError:
    user_input = input

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__file__)

VERSION = '1.0.0'
SUPPORTED_LICENSES = [
    'afl-3.0', 'agpl-3.0', 'apache-2.0', 'artistic-2.0', 'bsd-2-clause',
    'bsd-3-clause-clear', 'bsd-3-clause', 'bsl-1.0', 'cc-by-4.0',
    'cc-by-sa-4.0', 'cc0-1.0', 'ecl-2.0', 'epl-1.0', 'epl-2.0', 'eupl-1.1',
    'eupl-1.2', 'gpl-2.0', 'gpl-3.0', 'isc', 'lgpl-2.1', 'lgpl-3.0',
    'lppl-1.3c', 'mit', 'mpl-2.0', 'ms-pl', 'ms-rl', 'ncsa', 'ofl-1.1',
    'osl-3.0', 'postgresql', 'unlicense', 'upl-1.0', 'wtfpl', 'zlib'
]
SUPPORTED_CI_SERVICES = ['travis']


class CustomFormatter(
    argparse.RawTextHelpFormatter,
    argparse.ArgumentDefaultsHelpFormatter
):
    pass


def str_lower(s):
    return s.lower()


def get_cli_output(*args):
    out = subprocess.check_output(args)
    if sys.version_info[0] >= 3:
        out = out.decode()
    return out.strip()


def hyphenated(s):
    return re.sub('[ _]', '-', s.lower())


def snake_case(s):
    return re.sub('[ -]', '_', s.lower())


def derive_opt(opts, name, derived_from, transform=lambda x: x):
    if getattr(opts, name, None) is None:
        value = require_opt(opts, derived_from)
        setattr(opts, name, transform(value))
    return getattr(opts, name)


def require_opt(opts, name, _type=str):
    if getattr(opts, name, None) is None:
        prompt = '{}: '.format(name)
        value = _type(user_input(prompt))
        setattr(opts, name, value)
    return getattr(opts, name)


def columnize(lst):
    split = int(len(lst) / 3)
    lst1 = lst[0:split]
    lst2 = lst[split:split + split]
    lst3 = lst[split + split:]
    for row in zip_longest(lst1, lst2, lst3):
        yield '{:<20s} {:<20s} {}'.format(
            *(r if r is not None else '' for r in row)
        )


def display_help(parser, help_target):
    if help_target == '':
        parser.print_help()
    elif 'license' in help_target:
        print('Supported licenses:')
        for row in columnize(SUPPORTED_LICENSES):
            print(row)
        print('If no value is provided, MIT license is used.')
    else:
        print('No help available for "{}"'.format(help_target))
    raise SystemExit(0)


def create_setup_py(opts):
    template = """import subprocess
import sys
import setuptools
from {package_snakecase}.__version__ import VERSION


def changelog():
    log =  subprocess.check_output('bin/changelog')
    if sys.version_info[0] == 3:
        log = log.decode()
    return log


if __name__ == '__main__':
    with open("README.md", "r") as fh:
        long_description = fh.read()
    long_description += changelog() + '\\n'

    setuptools.setup(
        name="{package_snakecase}",
        version=VERSION,
        author="{author_name}",
        author_email="{author_email}",
        description=(
            "{description}"
        ),
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/{github_username}/{package_snakecase}",
        packages=setuptools.find_packages(),
        classifiers=(
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
        ),
        entry_points={{}},
        install_requires=[],
        include_package_data=True
    )
"""
    with open('setup.py', 'w') as f:
        f.write(template.format(
            description=require_opt(opts, 'description'),
            package_snakecase=derive_opt(
                opts, 'package_snakecase', 'package', snake_case
            ),
            github_username=require_opt(opts, 'github_username'),
            author_name=require_opt(opts, 'author_name'),
            author_email=require_opt(opts, 'author_email'),
        ))


def create_package_directory(opts):
    d = derive_opt(opts, 'package_snakecase', 'package', snake_case)
    os.makedirs(d, exist_ok=True)
    filepath = os.path.join(d, '__init__.py')
    with open(filepath, 'w') as f:
        f.write('from .__version__ import VERSION\n')
    filepath = os.path.join(d, '__version__.py')
    with open(filepath, 'w') as f:
        f.write("VERSION = '1.0.0'\n")


def create_travis_config(opts):
    template = """sudo: false

language: python

python:
- '2.7'
- '3.4'
- '3.5'
- '3.6'
- nightly

matrix:
  # Ignore failures for unstable versions
  allow_failures:
    - python: nightly

install:  - make init
  - python -m pip install -e .

before_script:
  - make lint

script:
  - make test

deploy:
  provider: pypi
  user: {pypi_username}
  password: $PYPI_PASSWORD
  on:
    branch: master
    tags: true
    distributions: sdist bdist_wheel
    repo: {github_username}/{package_snakecase}
    python: '3.6'
"""
    with open('.travis.yml', 'w') as f:
        f.write(template.format(
            pypi_username=require_opt(opts, 'pypi_username'),
            github_username=require_opt(opts, 'github_username'),
            package_snakecase=derive_opt(
                opts, 'package_snakecase', 'package', snake_case
            ),
        ))


def create_ci_config(opts):
    if opts.ci == 'travis':
        create_travis_config(opts)


def create_badge(alt_text, image, url):
    return '[![{}]({})]({})'.format(alt_text, image, url)


def create_travis_badge(opts):
    url = 'https://travis-ci.com/{}/{}'.format(
        require_opt(opts, 'travis_username'),
        derive_opt(opts, 'package_snakecase', 'package', snake_case),
    )
    image = '{}.svg?branch=master'.format(url)
    return create_badge('Build Status', image, url)


def create_pypi_badge(opts):
    image = 'https://img.shield.io/pypi/v/nine.svg'
    url = 'https://pypi.org/project/{}'.format(
        derive_opt(opts, 'package_hyphenated', 'package', hyphenated)
    )
    return create_badge('PyPI', image, url)


def create_readme_md(opts):
    template = """{badges}


# {package}
{description}


## Installation
```bash
pip install {package_hyphenated}
```
"""
    badges = []
    if opts.ci == 'travis':
        badges.append(create_travis_badge(opts))
    if not opts.no_pypi:
        badges.append(create_pypi_badge(opts))

    with open('README.md', 'w') as f:
        # f.write('\n'.join(body_lines))
        f.write(template.format(
            badges=''.join(badges),
            package=require_opt(opts, 'package'),
            description=require_opt(opts, 'description'),
            package_hyphenated=derive_opt(
                opts, 'package_hyphenated', 'package', hyphenated
            ),
        ))


def create_license_md(opts):
    resp = requests.get(
        'https://licenseapi.herokuapp.com/licenses/{}'.format(opts.license)
    )
    if resp.status_code != 200:
        logger.error('Unable to download license text')
        raise SystemExit(1)
    data = json.loads(resp.text)
    text = data['text']
    text = text.replace('[year]', opts.now.strftime('%Y'))
    text = text.replace('[fullname]', opts.author_name)
    with open('LICENSE', 'w') as f:
        f.write(text)


def build_cli():
    parser = argparse.ArgumentParser(
        formatter_class=CustomFormatter,
        add_help=False,
    )
    parser.add_argument(
        '-h', '--help', nargs='?', const='', metavar='OPTION', type=str_lower,
        help='\n'.join([
            'Show this message or get info about another option',
            'Ex: --help license',
        ]),
    )
    parser.add_argument(
        '--version',
        action='version',
        help='print version information',
        version='%(prog)s {} for Python {}'.format(
            VERSION,
            sys.version.split('\n')[0],
        ),
    )
    parser.add_argument(
        '-q', '--quiet', action='store_true'
    )
    parser.add_argument('-d', '--description')
    parser.add_argument(
        '-l', '--license', type=str_lower, nargs='?', const='mit',
        choices=SUPPORTED_LICENSES, metavar='LICENSE',
        help='Generate LICENSE; `--help license` for more info',
    )
    parser.add_argument(
        '-c', '--ci', type=str_lower, nargs='?', const='travis',
        choices=SUPPORTED_CI_SERVICES,
        help='Generate CI config'
    )
    parser.add_argument(
        'package', metavar='PACKAGE_NAME', nargs='?',
    )
    for arg in ['readme', 'package', 'pypi', 'setup']:
        parser.add_argument(
            '--no-{}'.format(arg), action='store_true', help=argparse.SUPPRESS
        )
    return parser


if __name__ == '__main__':
    parser = build_cli()

    opts = parser.parse_args()

    if opts.help is not None:
        display_help(parser, opts.help)

    setattr(opts, 'now', datetime.now())
    if getattr(opts, 'author_name', None) is None:
        author_name = get_cli_output('git', 'config', 'user.name')
        setattr(opts, 'author_name', author_name)
    if getattr(opts, 'author_email', None) is None:
        author_email = get_cli_output('git', 'config', 'user.email')
        setattr(opts, 'author_email', author_email)
    if opts.license is not None:
        create_license_md(opts)
    if not opts.no_readme:
        create_readme_md(opts)
    if not opts.no_package:
        create_package_directory(opts)
    if not opts.no_setup:
        create_setup_py(opts)
    if opts.ci:
        create_ci_config(opts)
