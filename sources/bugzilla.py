import requests
from lxml import html

from collections import OrderedDict, defaultdict
from html import escape
from io import StringIO


BZ_BASE = 'https://bugzilla.mozilla.org'
BUG_LINK = '[Bug {0}](https://bugzilla.mozilla.org/show_bug.cgi?id={0})'

# Activity Types
REPORTED = 'reported'
ATTACHMENTS = 'attachments'
NEEDINFO = 'needinfo'
DISCUSSED = 'discussed'
STATUS = 'status'
TAGGED = 'tagged'
METADATA = 'metadata'
TRIAGED = 'triaged'
OTHER = 'other'


class Bugzilla(object):
    def __init__(self, username, password, start, end):
        # We need to access /page.cgi, which is not part of the REST API.
        # For good data, we must simulate logging in and use cookies. Boo.
        print('Logging into Bugzilla...')
        response = requests.get(BZ_BASE + '/rest/login',
                                params={'login': username,
                                        'password': password,
                                        'restrict_login': True})

        if not response.ok:
            raise ValueError(response.json().get('message', 'Unknown Error'))

        print('Ok!\n')
        self.cookies = response.cookies

        self.start = start
        self.end = end

    def report(self, who):
        response = requests.get(BZ_BASE + '/page.cgi',
                                cookies=self.cookies,
                                params={
                                    'id': 'user_activity.html',
                                    'action': 'run',
                                    'group': 'bug',
                                    'who': who,
                                    'from': self.start.strftime('%Y-%m-%d'),
                                    'to': self.end.strftime('%Y-%m-%d'),
                                })

        if not response.ok:
            raise RuntimeError('Failed: %s' % response.text)

        return handle(response.content)


def handle(content):
    # Parse HTML
    tree = html.fromstring(content)
    rows = tree.cssselect('#report tr:not(#report-header)')

    # Prepare record structures
    activity = defaultdict(set)
    titles = dict()

    # Iterate over all returned rows, recording what actions occurred
    bug_id = None
    for tr in rows:
        (bug, when, what, old, new) = (td.text_content().strip() for td in tr)

        # Is this the start of a new bug?
        if bug:
            bug_id = bug
            title = tr.xpath('td[1]/a/@title')[0]
            titles[bug] = title.partition(' - ')[-1]

        # Record interactions with that bug
        action = classify(what, old, new)
        if action:
            activity[bug_id].add(action)

    # Report on the results
    return report(activity, titles)


def classify(what, old, new):
    ignore = [
        'CC', 'Hardware', 'Version', 'OS', 'Last Resolved', 'Ever confirmed'
    ]

    meta = [
        'Whiteboard', 'See Also', 'Blocks', 'Depends on', 'Keywords', 'Summary'
    ]

    if what in ignore:
        return None

    elif what == 'Bug ID' and old == '(new bug)':
        return REPORTED

    elif what.startswith('Attachment '):
        return ATTACHMENTS

    elif what == 'Flags' and (('needinfo' in new) or ('needinfo' in old)):
        return NEEDINFO

    elif what.startswith('Comment '):
        return DISCUSSED

    elif what in ['Status', 'Resolution']:
        return STATUS

    elif what == 'Keywords' and 'DevAdvocacy' in new:
        return TAGGED

    elif what == 'Whiteboard' and (('DevRel:P' in new) != ('DevRel:P' in old)):
        return TRIAGED

    elif what in meta:
        return METADATA

    else:
        print('Unhandled Interaction: %s\t%s\t%s' % (what, old, new))
        return OTHER


def report(activity, titles):
    descriptions = {
        REPORTED: 'Reported {} Bugs',
        ATTACHMENTS: 'Added or Modified Attachments on {} Bugs',
        NEEDINFO: 'Set or Cleared Needinfo? Flag on {} Bugs',
        DISCUSSED: 'Discussed {} Bugs',
        STATUS: 'Changed Status on {} Bugs',
        TAGGED: 'Tagged {} Bugs as DevAdvocacy',
        METADATA: 'Updated Metadata on {} Bugs',
        OTHER: 'Interacted with {} Other Bugs',
    }

    buglists = OrderedDict([
        (REPORTED, []),
        (ATTACHMENTS, []),
        (NEEDINFO, []),
        (DISCUSSED, []),
        (STATUS, []),
        (METADATA, []),
        (TAGGED, []),
        (OTHER, []),
    ])

    # Partition bugs into most significant bucket
    for (bug, actions) in activity.items():
        if REPORTED in actions:
            lst = buglists[REPORTED]
        elif ATTACHMENTS in actions:
            lst = buglists[ATTACHMENTS]
        elif NEEDINFO in actions:
            lst = buglists[NEEDINFO]
        elif DISCUSSED in actions:
            lst = buglists[DISCUSSED]
        elif STATUS in actions:
            lst = buglists[STATUS]
        elif TAGGED in actions:
            lst = buglists[TAGGED]
        elif METADATA in actions:
            lst = buglists[METADATA]
        elif OTHER in actions:
            lst = buglists[OTHER]
        elif TRIAGED in actions:
            # Skip bugs whose only change was triage
            continue
        else:
            print('Unrecognized logged action on Bug %s: %s' % (bug, actions))
            lst = buglists[OTHER]

        lst.append(bug)

    # Generate report
    s = StringIO()
    for (group, bugs) in buglists.items():
        if bugs:
            s.write('#### ' + descriptions[group].format(len(bugs)) + ':\n\n')
            for bug in sorted(bugs, key=int):
                link = BUG_LINK.format(bug)
                title = escape(titles[bug], quote=False)
                s.write('* %s - %s\n' % (link, title))
            s.write('\n')

    triaged = [k for k, v in activity.items() if TRIAGED in v]
    if triaged:
        s.write('#### Triaged {} DevAdvocacy Bugs\n\n'.format(len(triaged)))
        s.write('* _not listed_\n')

    return s.getvalue()
