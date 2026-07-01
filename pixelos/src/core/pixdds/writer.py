"""
PixDDS — DataWriter (publication sur un topic).
"""

import time
from typing import Any
from .topic import Topic, TopicData


class DataWriter:
    """Publie des données sur un topic DDS.

    Usage:
        writer.write({"x": 12.5, "y": 45.2})
        writer.write({"status": "OK"}, source_node="robot_02")
    """

    def __init__(self, topic: Topic, source_node: str):
        self.topic = topic
        self.source_node = source_node
        self._published_count = 0
        topic.attach_writer(self)

    def write(self, data: Any, source_node: str = None):
        """Publier un échantillon sur le topic."""
        sample = TopicData(
            topic_name=self.topic.name,
            source_node=source_node or self.source_node,
            data=data,
            sequence=self.topic._next_seq(),
        )
        self._published_count += 1
        self.topic.domain_id  # just to keep reference

        # Notify transport
        from .transport import _dispatch
        _dispatch(self.topic.name, self.topic.domain_id, sample)

    @property
    def published_count(self) -> int:
        return self._published_count

    def close(self):
        self.topic.detach_writer(self)

    def __repr__(self):
        return (f"DataWriter(node={self.source_node}, "
                f"topic={self.topic.name}, pub={self._published_count})")
