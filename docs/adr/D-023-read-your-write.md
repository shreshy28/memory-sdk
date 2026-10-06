# D-023: Bound explicit read-your-write

Status: Accepted

Explicit writes wait at most two seconds, use authorized canonical fallback when committed,
and otherwise return an explicit pending operation.
