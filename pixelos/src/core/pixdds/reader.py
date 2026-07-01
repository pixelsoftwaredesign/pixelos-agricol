"""
PixDDS — DataReader (souscription à un topic).
"""

import time
from typing import Callable, Optional, Any
from collections import deque
from .topic import Topic, TopicData


class DataReader:
    """Souscrit aux données publiées sur un topic DDS.

    Deux modes :
      - Callback : reader = topic.create_reader(callback=on_data)
      - Polling :  samples = reader.read()

    Usage:
        def on_pos(data, sample):
            print(f"Robot {sample.source_node}: {data}")

        reader = participant.create_reader(
            topic, callback=on_pos, qos=TopicQoS(...)
        )
    """

    def __init__(self, topic: Topic, source_node: str,
                 callback: Optional[Callable] = None):
        self.topic = topic
        self.source_node = source_node
        self.callback = callback
        self._queue: deque[TopicData] = deque(maxlen=100)
        self._received_count = 0
        topic.attach_reader(self)

    def on_data(self, sample: TopicData):
        """Appelé par le transport quand une donnée arrive."""
        self._queue.append(sample)
        self._received_count += 1
        if self.callback:
            try:
                self.callback(sample.data, sample)
            except Exception as e:
                print(f"[DataReader] callback error: {e}")

    def read(self, count: int = -1) -> list[TopicData]:
        """Lire les échantillons en attente (polling)."""
        if count < 0:
            samples = list(self._queue)
            self._queue.clear()
        else:
            samples = []
            for _ in range(min(count, len(self._queue))):
                samples.append(self._queue.popleft())
        return samples

    def wait_for_data(self, timeout: float = 1.0) -> Optional[TopicData]:
        """Attendre le prochain échantillon (bloquant)."""
        start = time.monotonic()
        while not self._queue:
            if time.monotonic() - start > timeout:
                return None
            time.sleep(0.001)
        return self._queue.popleft()

    @property
    def received_count(self) -> int:
        return self._received_count

    @property
    def available(self) -> int:
        return len(self._queue)

    def close(self):
        self.topic.detach_reader(self)
        self._queue.clear()

    def __repr__(self):
        return (f"DataReader(node={self.source_node}, "
                f"topic={self.topic.name}, rcvd={self._received_count})")
