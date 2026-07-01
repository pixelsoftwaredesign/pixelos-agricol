"""
Tests unitaires pour PixDDS.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.pixdds import (
    create_participant, DomainParticipant, DomainQoS,
    Topic, TopicQoS, DataWriter, DataReader,
    InProcessTransport, get_transport, set_transport,
)
from core.pixdds.qos import ReliabilityKind, DurabilityKind, HistoryKind
from core.pixdds.topic import TopicData


def test_create_participant():
    p = create_participant(domain_id=0, node_id="test_node")
    assert p is not None
    assert p.node_id == "test_node"
    assert p.domain_id == 0
    assert "topics" in p.status()
    assert "writers" in p.status()
    assert "readers" in p.status()
    p.close()


def test_custom_qos():
    qos = DomainQoS(heartbeat_ms=500, discovery_timeout_s=5, max_participants=10)
    p = DomainParticipant(domain_id=1, node_id="qos_test", qos=qos)
    assert p.qos.heartbeat_ms == 500
    assert p.qos.discovery_timeout_s == 5
    assert p.qos.max_participants == 10
    p.close()


def test_create_topic():
    p = create_participant(domain_id=0, node_id="topic_test")
    topic = p.create_topic("/test/topic")
    assert topic.name == "/test/topic"
    assert topic.domain_id == 0
    assert topic.writer_count == 0
    assert topic.reader_count == 0

    # Reuse existing topic
    topic2 = p.create_topic("/test/topic")
    assert topic is topic2
    p.close()


def test_topic_qos():
    qos = TopicQoS(
        reliability=ReliabilityKind.RELIABLE,
        durability=DurabilityKind.PERSISTENT,
        history=HistoryKind.KEEP_ALL,
        history_depth=50,
        deadline_ms=2000,
        lifespan_ms=60000,
        priority=10,
    )
    topic = Topic("/swarm/pos", domain_id=0, qos=qos)
    assert topic.qos.reliability == ReliabilityKind.RELIABLE
    assert topic.qos.durability == DurabilityKind.PERSISTENT
    assert topic.qos.history == HistoryKind.KEEP_ALL
    assert topic.qos.history_depth == 50
    assert topic.qos.deadline_ms == 2000
    assert topic.qos.lifespan_ms == 60000
    assert topic.qos.priority == 10


def test_writer_basic():
    p = create_participant(domain_id=0, node_id="writer_test")
    topic = p.create_topic("/test/writer")
    writer = p.create_writer(topic)
    assert writer.source_node == "writer_test"
    assert writer.published_count == 0
    writer.write({"msg": "hello"})
    assert writer.published_count == 1
    writer.write({"msg": "world"})
    assert writer.published_count == 2
    p.delete_writer(writer)
    assert writer not in p._writers
    p.close()


def test_writer_close():
    p = create_participant(domain_id=0, node_id="close_test")
    topic = p.create_topic("/test/close")
    writer = p.create_writer(topic)
    assert topic.writer_count == 1
    writer.close()
    assert topic.writer_count == 0
    p.close()


def test_reader_callback():
    received = []
    p = create_participant(domain_id=0, node_id="reader_cb")
    topic = p.create_topic("/test/callback")

    def cb(data, sample):
        received.append((data, sample.source_node, sample.sequence))

    reader = p.create_reader(topic, callback=cb)
    writer = p.create_writer(topic)

    writer.write({"a": 1})
    writer.write({"a": 2})
    writer.write({"a": 3})

    time.sleep(0.05)  # laisse le temps au dispatch
    assert len(received) == 3
    assert received[0][0] == {"a": 1}
    assert received[1][0] == {"a": 2}
    assert received[2][0] == {"a": 3}
    assert received[0][1] == "reader_cb"  # node_id du writer

    p.delete_reader(reader)
    p.delete_writer(writer)
    p.close()


def test_reader_poll():
    p = create_participant(domain_id=0, node_id="reader_poll")
    topic = p.create_topic("/test/poll")
    reader = p.create_reader(topic)
    writer = p.create_writer(topic)

    writer.write({"x": 10})
    writer.write({"x": 20})

    time.sleep(0.05)
    samples = reader.read()
    assert len(samples) == 2
    assert samples[0].data == {"x": 10}
    assert samples[1].data == {"x": 20}

    # After read, queue is empty
    assert reader.available == 0
    p.delete_reader(reader)
    p.delete_writer(writer)
    p.close()


def test_multi_reader():
    """Deux lecteurs sur le même topic reçoivent tous les messages."""
    received_a = []
    received_b = []

    p = create_participant(domain_id=0, node_id="multi")
    topic = p.create_topic("/test/multi")

    reader_a = p.create_reader(topic, callback=lambda d, s: received_a.append(d))
    reader_b = p.create_reader(topic, callback=lambda d, s: received_b.append(d))
    writer = p.create_writer(topic)

    writer.write({"val": 42})

    time.sleep(0.05)
    assert len(received_a) == 1
    assert len(received_b) == 1
    assert received_a[0] == {"val": 42}
    assert received_b[0] == {"val": 42}

    p.delete_reader(reader_a)
    p.delete_reader(reader_b)
    p.delete_writer(writer)
    p.close()


def test_multi_domain_isolation():
    """Deux domaines différents ne partagent pas les messages."""
    p0 = create_participant(domain_id=0, node_id="dom0")
    p1 = create_participant(domain_id=1, node_id="dom1")

    t0 = p0.create_topic("/test/iso")
    t1 = p1.create_topic("/test/iso")

    received = []
    reader = p1.create_reader(t1, callback=lambda d, s: received.append(d))
    writer = p0.create_writer(t0)

    writer.write({"secret": "dom0"})
    time.sleep(0.05)
    assert len(received) == 0  # dom1 ne voit pas dom0

    p0.close()
    p1.close()


def test_reader_close():
    p = create_participant(domain_id=0, node_id="reader_close")
    topic = p.create_topic("/test/rclose")
    reader = p.create_reader(topic)
    assert topic.reader_count == 1
    reader.close()
    assert topic.reader_count == 0
    p.close()


def test_multi_writer():
    """Plusieurs writers sur le même topic."""
    p = create_participant(domain_id=0, node_id="mw")
    topic = p.create_topic("/test/mw")
    received = []
    reader = p.create_reader(topic, callback=lambda d, s: received.append(d))
    w1 = p.create_writer(topic)
    w2 = p.create_writer(topic)
    w1.write({"from": "w1"})
    w2.write({"from": "w2"})
    time.sleep(0.05)
    assert len(received) == 2
    p.close()


def test_shared_topic_across_participants():
    """Deux participants dans le même domaine partagent les messages."""
    p1 = create_participant(domain_id=0, node_id="shared_a")
    p2 = create_participant(domain_id=0, node_id="shared_b")
    t1 = p1.create_topic("/swarm/shared")
    t2 = p2.create_topic("/swarm/shared")
    assert t1.name == t2.name

    received = []
    reader = p2.create_reader(t2, callback=lambda d, s: received.append(d))
    writer = p1.create_writer(t1)
    writer.write({"hello": "from_a"})

    import time
    time.sleep(0.05)
    assert len(received) == 1
    assert received[0] == {"hello": "from_a"}

    p1.close()
    p2.close()


def test_topic_data_auto_timestamp():
    td = TopicData(topic_name="/t", source_node="n", data={"k": "v"})
    assert td.timestamp > 0
    assert td.sequence == 0


def test_topic_data_custom_seq():
    td = TopicData(topic_name="/t", source_node="n", data={}, sequence=99)
    assert td.sequence == 99


def test_delete_topic():
    p = create_participant(domain_id=0, node_id="del_topic")
    topic = p.create_topic("/test/delete_me")
    assert p.get_topic("/test/delete_me") is topic
    p.delete_topic(topic)
    assert p.get_topic("/test/delete_me") is None
    p.close()


def test_participant_repr():
    p = create_participant(domain_id=0, node_id="repr_test")
    r = repr(p)
    assert "repr_test" in r
    assert "Domain" in r
    p.close()


def test_writer_repr():
    p = create_participant(domain_id=0, node_id="repr_w")
    topic = p.create_topic("/test/repr")
    w = p.create_writer(topic)
    r = repr(w)
    assert "repr_w" in r
    assert "/test/repr" in r
    p.close()


def test_reader_repr():
    p = create_participant(domain_id=0, node_id="repr_r")
    topic = p.create_topic("/test/repr")
    reader = p.create_reader(topic)
    r = repr(reader)
    assert "repr_r" in r
    assert "/test/repr" in r
    p.close()


def test_custom_transport():
    """On peut remplacer le transport global."""
    old = get_transport()
    custom = InProcessTransport()
    set_transport(custom)
    assert get_transport() is custom
    set_transport(old)
    assert get_transport() is old


def test_topic_repr():
    t = Topic("/test/tr", domain_id=0)
    r = repr(t)
    assert "/test/tr" in r
    assert "writers" in r


def test_high_throughput():
    """1000 messages passent rapidement."""
    p = create_participant(domain_id=0, node_id="perf")
    topic = p.create_topic("/test/perf")
    received = []
    reader = p.create_reader(topic, callback=lambda d, s: received.append(d))
    writer = p.create_writer(topic)

    n = 1000
    for i in range(n):
        writer.write({"i": i})

    time.sleep(0.3)
    assert len(received) == n
    assert received[0] == {"i": 0}
    assert received[-1] == {"i": n - 1}
    p.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK  {name}")
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                import traceback
                traceback.print_exc()
