#!/usr/bin/env python3

"""Historian discovers what you did last quarter."""

from datetime import datetime, timezone
from os import mkdir
from shutil import rmtree

from configobj import ConfigObj

import sources


def main():
    """Generate reports of online activity."""
    config = ConfigObj('config.ini', interpolation=False)

    # FIXME: Hardcoded start / end dates, currently 2016 Q2
    start = datetime(2016, 4, 1).replace(tzinfo=timezone.utc)
    end = datetime(2016, 7, 1).replace(tzinfo=timezone.utc)

    # Initialize all sources
    reporters = {}
    for source_name, params in config['Sources'].items():
        try:
            key = source_name.lower()
            constructor = sources.__getattribute__(source_name)
            reporters[key] = constructor(**params, start=start, end=end)
        except AttributeError:
            print('No source found: %s' % source_name)
            continue

    # Prepare a clean output directory
    rmtree('out', ignore_errors=True)
    mkdir('out')

    # Generate a report for each user
    for name, accounts in config['Users'].items():
        print('%s:' % name)

        with open('out/%s.md' % name, 'w') as f:
            for source, identity in accounts.items():
                if source not in reporters:
                    print('    - %s (skipped: source not enabled)' % source)
                    continue

                print('    - %s' % source)
                reporter = reporters[source]
                f.write('### %s\n\n' % reporter.__class__.__name__)
                f.write(reporter.report(identity))
                f.write('\n')

if __name__ == '__main__':
    main()
