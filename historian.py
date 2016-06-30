#!/usr/bin/env python3

"""Historian discovers what you did last quarter."""

from configparser import ConfigParser
from os import mkdir
from shutil import rmtree

from reporters import Bugzilla, GitHub


def main():
    """Generate reports of online activity."""
    config = ConfigParser()
    config.read('config.ini')

    creds = config['CREDENTIALS']
    bz = Bugzilla(creds['BugzillaUsername'], creds['BugzillaPassword'])
    gh = GitHub(creds['GitHubAPIKey'])

    # Remove the CREDENTIALS section to ease looping over all other sections
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

            ghuser = config[teammate]['github']
            if ghuser:
                print("    - GitHub")
                f.write('### GitHub\n\n')
                f.write(gh.report(ghuser, '2016-04-01', '2016-06-30'))
                f.write('\n')

if __name__ == '__main__':
    main()
