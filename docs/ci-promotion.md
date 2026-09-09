# CI and Automatic Promotion

TradeValue uses three environment workflows:

- `Dev` validates and auto-merges pull requests into `Dev`. After the resulting
  successful push, it opens or updates the `Dev → NonProd` promotion pull
  request.
- `NonProd` validates and auto-merges pull requests into `NonProd`. After the
  resulting successful push, it opens or updates the `NonProd → Prod`
  promotion pull request.
- `Prod` validates and auto-merges pull requests into `Prod`. It does not
  promote further.

All three call `_reusable-ci.yml`, so backend tests, ML tests, frontend lint,
frontend tests, and the frontend production build use the same implementation.
Each destination workflow owns the merge into its branch. Its merge job runs
only after that environment's required aggregate job succeeds. GitHub
auto-merge remains responsible for waiting on every other check required by the
destination branch, including Vercel preview checks when those are configured
as required. The Dev and NonProd push jobs only create the next promotion pull
request; they do not merge it themselves.

## Repository settings

### Pull request settings

Open **Settings → General → Pull Requests**:

1. Enable **Allow merge commits**.
2. Enable **Allow auto-merge**.

Auto-merge waits until all requirements on the destination branch have passed.
See [GitHub's auto-merge documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository).

### Actions secret

Open **Settings → Secrets and variables → Actions**:

1. Confirm that the repository secret `PROMOTION_TOKEN` exists. Its token must
   be scoped to this repository and have **Contents: Read and write** and
   **Pull requests: Read and write** permissions. Also grant **Workflows: Read
   and write** if automated promotions must merge pull requests that modify
   files under `.github/workflows/`.

The workflows use `PROMOTION_TOKEN` rather than `GITHUB_TOKEN` so pull requests
and merges created by the promotion job trigger the next GitHub Actions
workflow. Keep the default workflow permission at **Read repository contents
and packages**; the workflow does not need a broadly writable `GITHUB_TOKEN`.

### Branch rulesets

Open **Settings → Rules → Rulesets** and create three separate active branch
rulesets. A single ruleset cannot be used because each destination branch has a
different required check.

Configure each ruleset as follows:

- Enforcement status: **Active**
- Bypass list: empty
- Target: include one branch by exact name
- Enable **Restrict deletions**
- Enable **Require a pull request before merging**
- Required approvals: `0`
- Enable **Require status checks to pass before merging**
- Disable **Require branches to be up to date before merging**
- Keep force pushes blocked
- Do not enable **Restrict updates**
- Do not require deployments at this stage

Add only the check matching the target branch:

| Ruleset target | Required check |
| --- | --- |
| `Dev` | `Dev required` |
| `NonProd` | `NonProd required` |
| `Prod` | `Prod required` |

Strict up-to-date mode is intentionally disabled. Each downstream merge adds a
merge commit that is not present on the upstream environment branch. Requiring
the promotion branch to contain that downstream merge commit would stop the
next unattended promotion. The workflows instead serialize promotions and run
the complete destination check on every promotion pull request.

GitHub explains these options in its
[ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
and [required-status-check documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging).

## Safe rollout

1. Open or update a pull request into `Dev`. Confirm `Dev required` succeeds
   and the workflow enables auto-merge for the pull request.
2. Confirm GitHub merges into `Dev`, then creates the `Dev → NonProd` pull
   request and enables
   auto-merge. Confirm `NonProd required` appears and succeeds.
3. Confirm GitHub merges that pull request into `NonProd`, then creates the
   `NonProd → Prod` pull request. Confirm `Prod required` appears and succeeds.
4. Confirm GitHub merges the final pull request into `Prod`.

If a required job fails or is cancelled, the destination pull request remains
open. Rerun the failed jobs or push a corrective commit; auto-merge resumes only
after the destination workflow succeeds.
