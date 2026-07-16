from oluso.queue import OfflineQueue


def test_enqueue_and_process(tmp_path):
    q = OfflineQueue(10, str(tmp_path))
    q.enqueue({"message": "a"})
    q.enqueue({"message": "b"})
    assert q.size() == 2

    sent = []
    q.process_queue(lambda r: sent.append(r["message"]))

    assert q.is_empty()
    assert sent == ["a", "b"]


def test_max_size_evicts_oldest(tmp_path):
    q = OfflineQueue(2, str(tmp_path))
    q.enqueue({"message": "1"})
    q.enqueue({"message": "2"})
    q.enqueue({"message": "3"})
    assert q.size() == 2

    sent = []
    q.process_queue(lambda r: sent.append(r["message"]))
    assert sent == ["2", "3"]


def test_failure_stops_processing_and_requeues(tmp_path):
    q = OfflineQueue(10, str(tmp_path))
    q.enqueue({"message": "a"})
    q.enqueue({"message": "b"})

    call_count = 0

    def failing(_report):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("network down")

    q.process_queue(failing)

    assert call_count == 1
    assert q.size() == 2


def test_drops_after_three_failed_retries(tmp_path):
    q = OfflineQueue(10, str(tmp_path))
    q.enqueue({"message": "a"})

    def failing(_report):
        raise RuntimeError("network down")

    for _ in range(3):
        q.process_queue(failing)

    assert q.is_empty()


def test_persists_across_instances(tmp_path):
    q1 = OfflineQueue(10, str(tmp_path))
    q1.enqueue({"message": "persisted"})

    q2 = OfflineQueue(10, str(tmp_path))
    assert q2.size() == 1

    sent = []
    q2.process_queue(lambda r: sent.append(r["message"]))
    assert sent == ["persisted"]
