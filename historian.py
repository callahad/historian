#!/usr/bin/env python3

from bugzilla import BzReporter
from github import GhReporter

from configparser import ConfigParser
from os import mkdir
from shutil import rmtree


def main():
    config = ConfigParser()
    config.read('config.ini')

    creds = config['CREDENTIALS']
    bz = BzReporter(creds['BugzillaUsername'], creds['BugzillaPassword'])
    gh = GhReporter(creds['GitHubAPIKey'])
    config.remove_section('CREDENTIALS')

    # Prepare a clean output directory
    rmtree('out', ignore_errors=True)
    mkdir('out')

    for teammate in config.sections():
        print("%s:" % teammate)
        with open('out/%s.md' % teammate, 'w') as f:
            f.write('## %s\'s Q2 2016 Activity\n\n' % teammate)

            bugmail = config[teammate]['bugzilla']
            if bugmail:
                print("    - Bugzilla")
                f.write('### Bugzilla\n\n')
                f.write(bz.report(bugmail, '2016-04-01', '2016-06-30'))
                f.write('\n')

if __name__ == '__main__':
    main()
