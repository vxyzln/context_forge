from collections.abc import Sequence

from context_forge.git.models import GitActivitySummary, GitCommit


def summarize_commits(
    commits: Sequence[GitCommit],
) -> GitActivitySummary:
    authors: set[str] = set()
    files: set[str] = set()
    total_additions = 0
    total_deletions = 0

    for commit in commits:
        authors.add(commit.author)

        for change in commit.changes:
            files.add(change.path)
            total_additions += change.additions
            total_deletions += change.deletions

    return GitActivitySummary(
        total_commits=len(commits),
        total_authors=len(authors),
        files_changed=len(files),
        total_additions=total_additions,
        total_deletions=total_deletions,
    )
