import github3

from collections import defaultdict
from datetime import (datetime, timezone)
from itertools import groupby
from pprint import pprint

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


class GhReporter(object):
    def __init__(self, api_key):
        self.gh = github3.login(token=api_key)

    def report(self, who, start, end):
        fmt = '%Y-%m-%d'
        start = datetime.strptime(start, fmt).replace(tzinfo=timezone.utc)
        end = datetime.strptime(end, fmt).replace(tzinfo=timezone.utc)

        user = self.gh.user(who)

        all_events = list(user.iter_events())
        oldest = all_events[-1]
        if oldest.created_at >= start:
            msg = "Warning: May be missing valid events between %s and %s"
            print(msg % (datetime.strftime(start, fmt),
                         datetime.strftime(oldest.created_at, fmt)))

        events = [e for e in user.iter_events() if start <= e.created_at < end]

        good_events = []
        for event in events:
            if event.type in IGNORE_EVENTS:
                continue
            elif event.type in KEEP_EVENTS:
                good_events.append(event)
            else:
                print("Unhandled event type: %s" % event.type)

        k = lambda x: (x.repo[1], x.repo[0])
        for (repo, org), repo_events in groupby(sorted(good_events, key=k), k):
            print("\n#### %s/%s\n" % (org, repo))

            repo_events = list(repo_events)

            # Report on pushed commits
            pushes = defaultdict(int)
            for event in repo_events:
                if event.type == 'PushEvent':
                    num = event.payload['size']
                    ref = event.payload['ref'].split('/')[-1]
                    pushes[ref] += num

            for ref, count in sorted(pushes.items()):
                if count == 0:
                    continue
                noun = 'commit' if count == 1 else 'commits'
                print("pushed {} {} to {} branch".format(count, noun, ref))

            # Note: Not actually tested
            pages = set()
            for event in repo_events:
                if event.type == 'GollumEvent':
                    for page in event.payload['pages']:
                        pages.add(page.title)

            for page in sorted(pages):
                print("edited wiki page - {}".format(page))

            for event in repo_events:
                type = event.type
                if type == 'CommitCommentEvent':
                    print("commented on commit {comment.commit_id:.8}".format(**event.payload))
                elif type == 'GollumEvent':
                    continue
                elif type == 'IssueCommentEvent':
                    print("commented on issue {issue.number} - {issue.title}".format(**event.payload))
                elif type == 'IssuesEvent':
                    print("{action} issue #{issue.number} - {issue.title}".format(**event.payload))
                elif type == 'PublicEvent':
                    # Not actually tested...
                    print("made {repository.full_name} public".format(**event.payload))
                elif type == 'PullRequestEvent':
                    pr = event.payload['pull_request']

                    action = event.payload['action']
                    if action == "closed" and pr.to_json()['merged']:
                        action = "merged"

                    number = pr.number
                    user = pr.user.login
                    title = pr.title

                    print("{} pull request #{} by @{} - {}".format(action, number, user, title))
                elif type == 'PullRequestReviewCommentEvent':
                    print("{action} a comment on pull request #{pull_request.number} - {pull_request.title}".format(**event.payload))
                elif type == 'PushEvent':
                    continue
                elif type == 'ReleaseEvent':
                    # Not actually tested...
                    print("published release {}".format(event.payload['release'].name))
                else:
                    print("Unhandled event type: %s" % type)
