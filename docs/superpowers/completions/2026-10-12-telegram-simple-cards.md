# Simplified Telegram reviews

User-approved change: pending cards show the name and a short description with Open repo, Accept, Reject, and More. Accept explicitly authorizes publication with suggested metadata; separate field confirmations are no longer required. More expands details without changing the review or publishing.

Category selection preserves discovery suggestions, otherwise matches the name, description, and tags against existing category IDs, falling back to Utilities. Known free licenses can resolve an unset free-use status; unknown eligibility remains blocked. Description previews retain up to three sentences, bounded to 600 UTF-16 units, without changing stored descriptions. Cards display the selected category and known type, platforms, cost, and license; unknown fields are omitted. The collector's unverified Desktop app default is omitted unless explicitly selected or confirmed. Short repository descriptions are preserved without inventing features or audiences. No language-model call or new dependency is required.

Owner/chat binding, revision checks, expiry, NSFW blocking, publication pause, category validation, atomic publication, and replay protection remain enforced. Legacy callback actions remain supported for older cards.

Verification: all 62 disposable PostgreSQL/SQLite/transport tests passed using `backend/.venv/bin/python -m unittest discover -s backend/tests -q`. No schema migration required. Activation targets the local development worker and database only.
