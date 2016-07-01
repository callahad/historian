"""GitHub source adapter."""

import github3

from collections import defaultdict
from datetime import datetime
from itertools import groupby
from operator import attrgetter

from utils import partition


# See: https://developer.github.com/v3/activity/events/types/

KEEP_EVENTS = [
    'CommitCommentEvent',  # Creation of comment on commit
    'GollumEvent',  # Wiki page creation / update
    'IssueCommentEvent',  # Issue comment created / edited / deleted
    'IssuesEvent',  # Creation or metadata changes to an issue
    'PublicEvent',  # Private repository made open-source
    'PullRequestEvent',  # Creation or metadata changes on a pull request
    'PullRequestReviewCommentEvent',  # PR comment created / edited / deleted
    'PushEvent',  # Branch is pushed to
    'ReleaseEvent',  # Release is created
]

IGNORE_EVENTS = [
    # Obsolete
    'DownloadEvent'
    'FollowEvent'
    'ForkApplyEvent'
    'GistEvent'

    # Webhook Only
    'DeploymentEvent',  # Deployment
    'DeploymentStatusEvent',  # Deployment Status
    'MembershipEvent',  # User added / removed from a team
    'PageBuildEvent',  # Result of a gh-pages build
    'RepositoryEvent',  # Repo creation / deletion / visibility
    'StatusEvent',  # Commit status changes
    'TeamAddEvent',  # Repo added to a team

    # Inconsequential
    'CreateEvent',  # Creation of repo, branch, or tag
    'DeleteEvent',  # Deletion of branch or tag
    'ForkEvent',  # Forking of a repository
    'MemberEvent',  # Added as a collaborator to a repository
    'WatchEvent',  # User starred a repo
]

KNOWN_EVENTS = KEEP_EVENTS + IGNORE_EVENTS


class GitHub(object):
    """Connects to and reports on GitHub events."""

    def __init__(self, token, start, end):
        """Create a new, date-bounded GitHub source."""
        self.gh = github3.login(token=token)
        self.start = start
        self.end = end

    def report(self, who):
        """Generate a report of a given user's activity."""
        user = self.gh.user(who)

        # Only relevant dates
        events = prune(user.iter_events(), self.start, self.end)

        # Only known events, reporting any unknown
        events = filter_types(KNOWN_EVENTS, events, verbose=True)

        # Only events of whitelisted types
        events = filter_types(KEEP_EVENTS, events)

        # Group events by repository
        key = attrgetter('repo')
        for repo, events in groupby(sorted(events, key=key), key=key):
            repo = '/'.join(repo)

            print('#### %s\n' % repo)

            unused = events

            # Private -> Public Transitions, Software Releases
            lines, unused = handle_public_events(unused)
            print_group('Publications and Releases', lines)

            # Commit Pushes, Commit Comments
            lines, unused = handle_commit_events(unused)
            print_group('Commits and Comments', lines)

            # Pull Requests, Pull Request File / Line / General Comments
            lines, unused = handle_pr_events(unused, who)
            print_group('Pull Requests', lines)

            # Issues, Issue Comments
            lines, unused = handle_issue_events(unused)
            print_group('Issues', lines)

            # Wiki Updates
            lines, unused = handle_wiki_events(unused)
            print_group('Wiki', lines)

            for event in unused:
                print("Warning: Unused event of type %s" % event.type)

        return ''


# -- Event List Processors


def handle_public_events(iterable):
    """Report private repositories being made public, and new releases."""
    lines = []
    unused = iterable

    # Private -> Public Transitions
    events, unused = partition_type('PublicEvent', unused)
    for event in events:
        tmpl = 'made {} public'
        lines.append(tmpl.format('/'.join(event.repo)))

    # Releases
    events, unused = partition_type('ReleaseEvent', unused)
    for event in events:
        tmpl = 'published release: {}'
        lines.append(tmpl.format(event.payload['release'].name))

    return (lines, unused)


def handle_commit_events(iterable):
    """Report pushes and commit comments."""
    lines = []
    unused = iterable

    # Pushes
    counts = defaultdict(int)
    events, unused = partition_type('PushEvent', unused)
    for event in events:
        num = event.payload['size']
        branch = event.payload['ref'].split('/')[-1]

        if num == 0:
            continue

        counts[branch] += num

    for (branch, count) in sorted(counts.items()):
        noun = 'commit' if count == 1 else 'commits'

        tmpl = 'pushed {} {} to branch {}'
        lines.append(tmpl.format(count, noun, branch))

    # Commit Comments
    events, unused = partition_type('CommitCommentEvent', unused)
    for event in events:
        tmpl = 'commented on commit {:.8}'
        lines.append(tmpl.format(event.payload['comment'].commit_id))

    return (lines, unused)


def handle_pr_events(iterable, who=None):
    """Report pull request changes and comments."""
    lines = []
    unused = iterable

    actions = defaultdict(list)

    # Pull Requests
    events, unused = partition_type('PullRequestEvent', unused)
    for event in sorted(events, key=lambda event: event.created_at):
        pr = event.payload['pull_request']

        number = pr.number
        title = pr.title
        user = pr.user.login

        action = event.payload['action']
        if action == 'closed' and pr.to_json()['merged']:
            action = 'merged'

        if user == who:
            action = 'proposed' if action == 'opened' else action
            action = 'rescinded' if action == 'closed' else action

        key = (number, user, title)
        actions[key].append(action)

    # Pull Request General Comments
    events, unused = partition(is_pr_comment, unused)
    for event in sorted(events, key=lambda event: event.created_at):
        if event.payload['action'] == 'deleted':
            continue

        pr = event.payload['issue']

        number = pr.number
        title = pr.title
        user = pr.user.login

        key = (number, user, title)
        actions[key].append('discussed')

    # Pull Request File / Line Comments
    events, unused = partition_type('PullRequestReviewCommentEvent', unused)
    for event in sorted(events, key=lambda event: event.created_at):
        if event.payload['action'] == 'deleted':
            continue

        pr = event.payload['pull_request']

        number = pr.number
        title = pr.title
        user = pr.user.login

        key = (number, user, title)
        actions[key].append('discussed')

    for (number, user, title), actions in sorted(actions.items()):
        summary = grammatical_join(list(uniq(actions)))

        if user == who:
            tmpl = '{} pull request #{} - {}'
            lines.append(tmpl.format(summary, number, title))
        else:
            tmpl = '{} pull request #{} by @{} - {}'
            lines.append(tmpl.format(summary, number, user, title))

    return (lines, unused)


def handle_issue_events(iterable):
    """Report issue changes and comments."""
    lines = []
    unused = iterable

    actions = defaultdict(list)

    # Issues
    events, unused = partition_type('IssuesEvent', unused)
    for event in events:
        number = event.payload['issue'].number
        title = event.payload['issue'].title

        key = (number, title)
        actions[key].append(event.payload['action'])

    # Issue Comments
    events, unused = partition(is_issue_comment, unused)
    for event in events:
        if event.payload['action'] == 'deleted':
            continue

        number = event.payload['issue'].number
        title = event.payload['issue'].title

        key = (number, title)
        actions[key].append('discussed')

    for (number, title), actions in sorted(actions.items()):
        summary = grammatical_join(list(uniq(actions)))

        tmpl = '{} issue #{} - {}'
        lines.append(tmpl.format(summary, number, title))

    return (lines, unused)


def handle_wiki_events(iterable):
    """Report wiki updates."""
    lines = []
    unused = iterable

    pages = set()

    events, unused = partition_type('GollumEvent', unused)
    for event in events:
        for page in event.payload['pages']:
            pages.add(page.title)

    for page in sorted(pages):
        tmpl = 'edited wiki page - {}'
        lines.append(tmpl.format(page))

    return (lines, unused)


# -- Local Helpers


def prune(iterable, start, end):
    """Discard events that fall outside the start-end interval."""
    events = sorted(iterable, key=lambda event: event.created_at)
    events.reverse()

    # Check if we have at least one event older than the start date.
    # If so, then we have a complete record for the desired interval.
    oldest_event = events[-1]
    if oldest_event.created_at >= start:
        msg = 'Warning: May be missing valid events between %s and %s'
        print(msg % (datetime.strftime(start, '%Y-%m-%d'),
                     datetime.strftime(oldest_event.created_at, '%Y-%m-%d')))

    return (event for event in iterable if start <= event.created_at < end)


def filter_types(types, iterable, verbose=False):
    """Filter events that match several types."""
    known, unknown = partition(lambda event: event.type in types, iterable)

    if verbose:
        for event in unknown:
            print('Warning: Ignored or unknown event type: %s' % event.type)

    return known


def partition_type(typ, lst):
    """Split an event list into two lists based on event.type."""
    return partition(lambda event: event.type == typ, lst)


def is_issue_comment(event):
    """Determine if a comment applies to an issue."""
    try:
        right_type = event.type == 'IssueCommentEvent'
        right_payload = 'pull_request' not in event.payload['issue'].to_json()
        return right_type and right_payload
    except (KeyError, IndexError, AttributeError, TypeError):
        return False


def is_pr_comment(event):
    """Determine if a comment applies to a pull request."""
    try:
        right_type = event.type == 'IssueCommentEvent'
        right_payload = 'pull_request' in event.payload['issue'].to_json()
        return right_type and right_payload
    except (KeyError, IndexError, AttributeError, TypeError):
        return False


def print_group(header, lines):
    """Print all lines in an array, prepending '* ' to each line."""
    lines = list(lines)

    if lines:
        print('%s:\n' % header)
        for line in lines:
            print('* %s' % line)
        print()


def grammatical_join(words):
    """Join a list of words, using an oxford comma if appropriate."""
    if '__getitem__' not in words:
        words = list(words)

    if len(words) == 2:
        return ' and '.join(words)
    else:
        words = words[:-2] + [', and '.join(words[-2:])]
        return ', '.join(words)


def uniq(iterable):
    """Filter consecutively repeated elements in an iterable."""
    previous = None

    for item in iterable:
        if item == previous:
            continue

        previous = item
        yield item
