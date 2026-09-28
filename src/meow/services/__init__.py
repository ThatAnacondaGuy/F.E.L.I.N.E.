"""Use cases on top of storage.

Public mutating functions commit and write an audit entry. Helpers named ``create_*``
join the caller's transaction instead, so a proposal and its effect commit together.
"""
