# B-Square Catch-Up Plan (April 15, 2026)

This note is for catching `B-Square-Bulletin/community-calendar` up with upstream
`judell/community-calendar` while minimizing conflict resolution work.

## Current shape

As of April 15, 2026, the locally known branch state is:

- Upstream `main` is 37 commits ahead of `bsquare/main`
- `bsquare/main` has 10 commits not in upstream

Most of those 10 downstream-only commits are not substantive:

- 5 are `Auto-generate calendar metadata`
- 1 is a merge commit
- 1 is a large "keep only bloomington" pruning commit

The substantive downstream-only commits are:

- `39334d16c9288f835cac122344e4c432e68ff004`  
  `chore: ignore .env and .envrc files`
- `a19fd0c8a8b42cb7890c1775d2bb0bfdc9832276`  
  `feat(classifier): add rate limiting and retry logic for API calls`
- `aed104ba243e1165f4461efdd9ecadfe88089456`  
  `fix: use correct headers for rate limits`

The large pruning commit is:

- `4c724d4344dfe104ace70dfe1a3228fe1f82a484`  
  `Sync with upstream and keep only bloomington`

## Recommendation

Do **not** merge the current `bsquare/main` straight into current upstream.

The lower-friction path is:

1. Start a fresh catch-up branch from current upstream `main`
2. Replay only the 3 substantive downstream commits
3. Recreate the Bloomington-only pruning as a **fresh commit on top of current upstream**
   instead of cherry-picking the old pruning commit verbatim

This avoids dragging along:

- metadata-only commits
- an old merge commit
- a very large delete-heavy commit based on an older tree

## Suggested commands

Assuming Josh is in a clone where:

- `origin` = `B-Square-Bulletin/community-calendar`
- `upstream` = `judell/community-calendar`

```bash
git fetch origin
git fetch upstream

git checkout -b catchup-2026-04-15 upstream/main

git cherry-pick 39334d16c9288f835cac122344e4c432e68ff004
git cherry-pick a19fd0c8a8b42cb7890c1775d2bb0bfdc9832276
git cherry-pick aed104ba243e1165f4461efdd9ecadfe88089456
```

At that point the branch has:

- current upstream behavior and schema/workflow changes
- B-Square's classifier retry/rate-limit improvements
- B-Square's `.env` ignore rules

The classifier rate-limiting work should be treated as legitimate downstream
product code, not a fork-only hack. The immediate goal is to replay it cleanly
so B-Square can keep moving. After the catch-up settles, Josh should be able to
offer those classifier commits back upstream as a normal PR with a much smaller
review surface.

## Bloomington-only follow-up

If B-Square still wants to keep the repo Bloomington-only, prefer making a new
pruning commit from the fresh catch-up branch instead of cherry-picking:

`4c724d4344dfe104ace70dfe1a3228fe1f82a484`

Reason:

- that old commit deletes many files that have changed upstream since the split
- replaying the deletes as a fresh commit is easier to reason about than
  resolving delete/modify conflicts from an old patch

If Josh wants the fastest path, he can also defer the pruning step entirely and
land the upstream catch-up first.

## Expected conflict surface

From the locally known merge base, the true overlap between upstream and
downstream work is small:

- `cities.json`
- `cities/toronto/SOURCES_CHECKLIST.md`
- `report.json`
- `xmlui/version.txt`

That means the 3 small cherry-picks above should be much easier than a raw
merge of the divergent branch tips.

## Safe commits to skip

These do not need to be replayed:

- `1633c6de` `Auto-generate calendar metadata`
- `48fd3466` `Auto-generate calendar metadata`
- `7e6824d0` `Auto-generate calendar metadata`
- `920b8cae` `Auto-generate calendar metadata`
- `37375424` `Auto-generate calendar metadata`
- `912b930f` merge commit

## Practical sequence

If the goal is to make review easy:

1. Open a PR from `catchup-2026-04-15` into `bsquare/main`
2. Keep the first PR limited to upstream catch-up + the 3 small downstream replays
3. If needed, do Bloomington-only pruning in a second PR

That split keeps the first review about code and behavior, and the second about
repo scope.

## Supabase catch-up

Josh has his own Supabase project, so Git catch-up and Supabase catch-up should
be treated as related but separate tasks.

### Keep B-Square's own project config

These should stay B-Square-specific:

- Supabase project ref / URL
- publishable key / anon key
- service-role key
- edge-function secrets
- GitHub Actions secrets and variables tied to the B-Square project
- any dashboard-only project settings

For config-file conflicts, keep B-Square's values in:

- `xmlui/config.json`
- `xmlui/config.local.js`
- any local `.env`-style files

### Recommended order

1. Catch up the Git branch first
2. Deploy or sync code changes that are environment-agnostic
3. Apply the repo's DDL/functions as the intended source of truth
4. Apply only the missing database objects and indexes
5. Verify edge functions and their environment variables

The intended contract is that the repo's DDL and function definitions are
authoritative. Josh should be able to assume that applying the database objects
defined here is the correct way to catch up his Supabase project.

If upstream production ever diverges from the checked-in DDL, that should be
treated as upstream drift to fix in this repo, not as a downstream burden for
B-Square to work around.

### Minimum Supabase path

Josh should not have to think in terms of individual tables, RPCs, and indexes.

The simple path is:

1. Keep B-Square's own Supabase URL, keys, secrets, and env vars
2. Apply the repo's checked-in DDL and function definitions
3. Deploy the edge functions the current app expects
4. Open the app and do a quick smoke test

If that works, he is done.

For this repo as of April 15, 2026, the edge-function picture is:

- `load-events`
  Required for the scheduled/event-ingest path
- `my-picks`
  Required if B-Square wants shareable/exportable picks feeds
- `capture-event`
  Required if B-Square wants poster/image/audio capture
- `validate-feed`
  Required for the feed-management UI
- `chat-events`
  Optional unless B-Square is using the chat/event-assistant feature

So the practical default is:

1. Redeploy `load-events`, `my-picks`, `capture-event`, and `validate-feed`
2. Redeploy `chat-events` only if that feature is in use

For these functions, Josh should also preserve B-Square-specific secrets and env
vars rather than copying upstream values.

As of April 15, 2026, the Sources panel no longer depends on a
`get_source_counts` RPC. It computes source counts from the already-loaded
event list in the client, so that specific function is not part of the minimum
catch-up path.

### Only if something breaks

Only drop to object-level checking if the app still fails after the normal
catch-up path.

The first things to inspect then are:

- feed-management objects such as `feeds` and `remove_feed`
- the `deduplicated_events` object and `refresh_deduplicated_events()`
- supporting indexes if event loading is unexpectedly slow

### Practical guidance

The safe model is:

- upstream code changes are usually portable
- Supabase credentials are not portable
- database object definitions in the repo are intended to be portable and
  authoritative

So Josh should not copy upstream credentials, but he should be able to rely on
the checked-in DDL and function definitions as the correct database catch-up
path for the B-Square project.
