# Security Policy

If a secret is accidentally committed:

1. Rotate the secret immediately with the provider (e.g., Google API key).
2. Revoke the leaked credential if possible.
3. Rewrite git history to remove the secret using `git filter-repo`.
4. Force-push to all branches/tags that contained the leak.
5. Invalidate caches (e.g., GitHub forks/Actions caches) if required.
6. Audit access logs for suspicious activity.
7. Open an incident ticket and document remediation.

## Git history rewrite quick steps

- Create `.git-rewrite-replacements.txt` with the exact leaked value:
  - Example: `leaked-value==>REDACTED`
- Run: `git filter-repo --force --replace-text .git-rewrite-replacements.txt`
- Add remote back if removed and force push: `git remote add origin <url>` then `git push --force --all` and `git push --force --tags`.

## Prevention

- Keep `.env` files untracked; commit only `.env.example` with placeholders.
- Use pre-commit hooks and secret scanners.
- Prefer environment variables and secret managers in CI/CD.
