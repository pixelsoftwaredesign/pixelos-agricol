"""
PixDDS — Routes Flask pour le dashboard swarm.
"""

import json
from flask import jsonify, request, render_template
from . import create_participant

_participants = {}
_default_participant = create_participant(domain_id=0, node_id="swarm_gateway")
_default_topic = _default_participant.create_topic("/swarm/heartbeat")


def register_pixdds_routes(app):
    @app.route("/pixdds/status")
    def dds_status():
        p = _default_participant
        return jsonify(p.status())

    @app.route("/pixdds/peers")
    def dds_peers():
        p = _default_participant
        peers = [peer.to_dict() for peer in p.get_peers()]
        return jsonify({"count": len(peers), "peers": peers})

    @app.route("/pixdds/topics")
    def dds_topics():
        p = _default_participant
        topics = []
        for t in p._topics.values():
            topics.append({
                "name": t.name,
                "domain": t.domain_id,
                "writers": t.writer_count,
                "readers": t.reader_count,
            })
        return jsonify({"count": len(topics), "topics": topics})

    @app.route("/pixdds/publish", methods=["POST"])
    def dds_publish():
        body = request.get_json(force=True)
        topic_name = body.get("topic", "/swarm/heartbeat")
        data = body.get("data", {})
        topic = _default_participant.get_topic(topic_name)
        if not topic:
            topic = _default_participant.create_topic(topic_name)
        writer = _default_participant.create_writer(topic)
        writer.write(data)
        _default_participant.delete_writer(writer)
        return jsonify({"status": "ok", "topic": topic_name, "data": data})

    @app.route("/pixdds/subscribe", methods=["POST"])
    def dds_subscribe():
        body = request.get_json(force=True)
        topic_name = body.get("topic", "/swarm/heartbeat")
        topic = _default_participant.get_topic(topic_name)
        if not topic:
            topic = _default_participant.create_topic(topic_name)
        results = []

        def _cb(data, sample):
            results.append({
                "data": data,
                "source": sample.source_node,
                "seq": sample.sequence,
                "ts": sample.timestamp,
            })

        reader = _default_participant.create_reader(topic, callback=_cb)
        return jsonify({
            "status": "subscribed",
            "topic": topic_name,
            "reader": str(reader),
        })

    @app.route("/pixdds/messages/<path:topic_name>")
    def dds_messages(topic_name):
        p = _default_participant
        if not topic_name.startswith("/"):
            topic_name = "/" + topic_name
        topic = p.get_topic(topic_name)
        if not topic:
            return jsonify({"count": 0, "messages": []})
        for reader in p._readers:
            if reader.topic.name == topic.name:
                samples = reader.read()
                return jsonify({
                    "count": len(samples),
                    "messages": [
                        {
                            "source": s.source_node,
                            "data": s.data,
                            "seq": s.sequence,
                            "ts": s.timestamp,
                        }
                        for s in samples
                    ],
                })
        return jsonify({"count": 0, "messages": []})

    @app.route("/pixdds/dashboard")
    def dds_dashboard():
        return render_template("pixdds.html")
