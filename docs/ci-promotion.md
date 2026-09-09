# CI and Automatic Promotion

TradeValue uses three environment workflows:

- `Dev` validates pull requests into and pushes to `Dev`. After a successful
  push, it opens or updates the `Dev → NonProd` promotion pull request.
- `NonProd` validates pull requests into and pushes to `NonProd`. After a
  successful push, it opens or updates the `NonProd → Prod` promotion pull
  request.
- `Prod` validates pull requests into and pushes to `Prod`. It does not promote
  further.

All three call `_reusable-ci.yml`, so backend tests, ML tests, frontend lint,
frontend tests, and the frontend production build use the same implementation.
Promotion is disabled unless the repository variable
`ENABLE_AUTO_PROMOTION` is exactly `true`.

## Repository settings

### Pull request settings

Open **Settings → General → Pull Requests**:

1. Enable **Allow merge commits**.
2. Enable **Allow auto-merge**.

Auto-merge waits until all requirements on the destination branch have passed.
See [GitHub's auto-merge documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository).

### Actions secret and variable

Open **Settings → Secrets and variables → Actions**:

1. Confirm that the repository secret `PROMOTION_TOKEN` exists. Its token must
   be scoped to this repository and have **Contents: Read and write** and
   **Pull requests: Read and write** permissions. Also grant **Workflows: Read
   and write** if automated promotions must merge pull requests that modify
   files under `.github/workflows/`.
2. Create the repository variable `ENABLE_AUTO_PROMOTION` with the value
   `false`. Change it to `true` only after all rulesets below are active and a
   controlled promotion has succeeded.

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

1. Keep `ENABLE_AUTO_PROMOTION=false`.
2. Merge the workflow changes into `Dev` and confirm `Dev required` appears
   and succeeds.
3. Create a `Dev → NonProd` pull request manually. Confirm `NonProd required`
   appears and succeeds, then merge it.
4. Create a `NonProd → Prod` pull request manually. Confirm `Prod required`
   appears and succeeds, then merge it.
5. Add the three required checks to their matching rulesets if they were not
   selectable before their first runs.
6. Set `ENABLE_AUTO_PROMOTION=true`.
7. Push one controlled documentation-only change through `Dev` and confirm it
   advances automatically to `NonProd` and then `Prod`.

If a required job fails or is cancelled, the destination pull request remains
open. Rerun the failed jobs or push a corrective commit; auto-merge resumes only
after the destination workflow succeeds.
