import github3

from utils import partition

from collections import defaultdict

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
    def __init__(self, token, start, end):
        self.gh = github3.login(token=token)
        self.start = start
        self.end = end

    def report(self, who):
        user = self.gh.user(who)

        all_events = list(user.iter_events())
        all_events.sort(key=lambda e: e.created_at, reverse=True)

        oldest = all_events[-1]
        if oldest.created_at >= self.start:
            msg = 'Warning: May be missing valid events between %s and %s'
            print(msg % (datetime.strftime(self.start, fmt),
                         datetime.strftime(oldest.created_at, fmt)))

        events = [e for e in user.iter_events()
                  if self.start <= e.created_at < self.end]

        known, unknown = partition(lambda e: e.type in KNOWN_EVENTS, events)
        for event in unknown:
            print('Warning: Unrecognized event type: %s' % event.type)

        kept, ignored = partition(lambda e: e.type in KEEP_EVENTS, known)

        rest = kept

        # Report All Private -> Public Repository Transitions
        matches, rest = partitiontype('PublicEvent', rest)
        for event in matches:
            tmpl = '* made {repository.full_name} public'
            print(tmpl.format(**event.payload))

        # Report All Pull Request Interactions
        data = []

        matches, rest = partitiontype('PullRequestEvent', rest)
        for event in matches:
            pr = event.payload['pull_request']

            repo = '/'.join(event.repo)
            when = event.created_at
            num = pr.number
            user = pr.user.login
            title = pr.title

            action = event.payload['action']
            if action == 'closed' and pr.to_json()['merged']:
                action = 'merged'

            data.append((repo, num, when, action, user, title))

        matches, rest = partition(is_pr_comment, rest)
        for event in matches:
            issue = event.payload['issue']

            repo = '/'.join(event.repo)
            when = event.created_at
            num = issue.number
            user = issue.user.login
            title = issue.title

            action = event.payload['action']
            if action == 'created':
                action = 'discussed'

            data.append((repo, num, when, action, user, title))

        matches, rest = partitiontype('PullRequestReviewCommentEvent', rest)
        for event in matches:
            if event.payload['action'] == 'deleted':
                continue

            pr = event.payload['pull_request']

            repo = '/'.join(event.repo)
            when = event.created_at
            num = pr.number
            user = pr.user.login
            title = pr.title

            action = 'discussed'

            data.append((repo, num, when, action, user, title))

        for repo, num, _, action, user, title in sorted(data):
            tmpl = '* {action} pull request {repo}#{num} by @{user} - {title}'
            print(tmpl.format(**locals()))

        # Report All Issues and Issue Comments
        data = []

        matches, rest = partitiontype('IssuesEvent', rest)
        for event in matches:
            repo = '/'.join(event.repo)
            when = event.created_at
            num = event.payload['issue'].number
            title = event.payload['issue'].title
            action = event.payload['action']

            data.append((repo, num, when, action, title))

        matches, rest = partition(is_issue_comment, rest)
        for event in matches:
            if event.payload['action'] == 'deleted':
                continue

            repo = '/'.join(event.repo)
            when = event.created_at
            num = event.payload['issue'].number
            title = event.payload['issue'].title
            action = 'discussed'

            data.append((repo, num, when, action, title))

        for repo, num, _, action, title in sorted(data):
            tmpl = '* {action} issue {repo}#{num} - {title}'
            print(tmpl.format(**locals()))

        # Report all Commits
        data = defaultdict(int)

        matches, rest = partitiontype('PushEvent', rest)
        for event in matches:
            num = event.payload['size']
            repo = '/'.join(event.repo)
            branch = event.payload['ref'].split('/')[-1]

            if num == 0:
                continue

            data[(repo, branch)] += num

        for (repo, branch), count in sorted(data.items()):
            noun = 'commit' if count == 1 else 'commits'

            tmpl = '* pushed {} {} to {} branch {}'
            print(tmpl.format(count, noun, repo, branch))

        # Report all Commit Comments
        matches, rest = partitiontype('CommitCommentEvent', rest)
        for event in matches:
            repo = '/'.join(event.repo)
            sha = event.payload['comment'].commit_id

            tmpl = '* commented on commit {:.8} in {}'
            print(tmpl.format(sha, repo))

        # Report on all Wiki updates
        data = defaultdict(set)

        matches, rest = partitiontype('GollumEvent', rest)
        for event in matches:
            repo = '/'.join(event.repo)

            for page in event.payload('pages'):
                data[repo].add(page.title)

        for repo, page in sorted(data.items()):
            tmpl = '* edited {} wiki page - {}'
            print(tmpl.format(repo, page))

        # Report on all Release events
        data = defaultdict(set)

        matches, rest = partitiontype('ReleaseEvent', rest)
        for event in matches:
            repo = '/'.join(event.repo)
            name = event.payload['release'].name

            data[repo].add(name)

        for repo, release in sorted(data.items()):
            tmpl = '* published release of {} - {}'
            print(tmpl.format(repo, release))

        return 'Incomplete'


# -- Local Helpers

def partitiontype(type, lst):
    return partition(lambda event: event.type == type, lst)


def is_issue_comment(event):
    try:
        right_type = event.type == 'IssueCommentEvent'
        right_payload = 'pull_request' not in event.payload['issue'].to_json()
        return right_type and right_payload
    except (KeyError, IndexError, AttributeError, TypeError):
        return False


def is_pr_comment(event):
    try:
        right_type = event.type == 'IssueCommentEvent'
        right_payload = 'pull_request' in event.payload['issue'].to_json()
        return right_type and right_payload
    except (KeyError, IndexError, AttributeError, TypeError):
        return False
