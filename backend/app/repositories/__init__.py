"""Data-access layer: SQLAlchemy queries live here, not in route handlers.

Repositories never commit; the caller (service/use case) owns the transaction.
Every query on user-owned data must be scoped by the authenticated user's id.

Migration status: ``UserRepository`` is the first repository. Other domains
still query from ``app/api/*`` and ``app/services/*`` and will be moved here
incrementally, one domain per change.
"""
