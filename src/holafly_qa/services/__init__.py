"""Service layer — the logic that commands use to do actual work.

Services are pure Python (no CLI, no printing). They can be imported and
reused by any command, the GUI, or tests. Keeping logic here instead of
in the command files means we never duplicate code and everything is
easy to test.
"""