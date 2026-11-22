# Issue Tracker

This repo uses **GitHub Issues** for issue tracking.

## Commands

Create an issue:
```bash
gh issue create --title "Title" --body "Description"
```

List issues:
```bash
gh issue list
```

View an issue:
```bash
gh issue view <number> --comments
```

Close an issue:
```bash
gh issue close <number>
```

Add labels:
```bash
gh issue edit <number> --add-label "label-name"
```

## Notes

- Use the `gh` CLI for all issue operations
- Read the comments with the body. Triage records its Agent Brief as a comment,
  and that brief can override the body's proposed fix.
- Issues are visible at `https://github.com/B-Square-Bulletin/community-calendar/issues`
