"""Two simultaneous requests for the same manager slot: exactly one must win.

Requests run in parallel threads; the server handles each in its own worker thread
with its own SQLite connection. Correctness comes from BEGIN IMMEDIATE in
write_transaction: the second request waits for the lock and then sees the first meeting.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import MONDAY_10_00, book, make_company, make_manager


def test_same_slot_booked_concurrently_only_once(client, db):
    manager = make_manager(client)
    companies = [make_company(client) for _ in range(8)]
    start = threading.Barrier(len(companies))

    def attempt(company_id: int) -> int:
        start.wait()  # release all requests at the same moment
        return book(client, company_id, manager, MONDAY_10_00).status_code

    with ThreadPoolExecutor(max_workers=len(companies)) as pool:
        statuses = list(pool.map(attempt, companies))

    assert sorted(statuses) == [201] + [409] * (len(companies) - 1)
    assert db.execute("SELECT COUNT(*) FROM meetings WHERE manager_id = ?", (manager,)).fetchone()[0] == 1
