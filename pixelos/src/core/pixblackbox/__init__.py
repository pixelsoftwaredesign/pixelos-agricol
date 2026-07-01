"""
PixBlackBox — Enregistreur de vol Pixel OS.

Stocke tous les événements du cycle de maintenance autonome
dans un format binaire compact (.pxbb) avec index mémoire
pour les requêtes temporelles et l'export CSV.
"""

import os
import io
import csv
import json
import struct
import time
import zlib
import threading
from typing import Optional, Iterator
from io import BytesIO
from dataclasses import dataclass, field
from pathlib import Path


# ── Format binaire ─────────────────────────────────────────
# [4B magic "PXBB"] [2B version] [2B header_reserved]
# — records répétés :
#   [1B record_type] [8B timestamp_us] [4B payload_len BE]
#   [payload_len B: JSON UTF-8]
# — [4B CRC32 footer]
# ────────────────────────────────────────────────────────────

PXBB_MAGIC = b"PXBB"
PXBB_VERSION = 1
HEADER_SIZE = 8  # magic(4) + version(2) + reserved(2)
RECORD_OVERHEAD = 13  # type(1) + timestamp(8) + length(4)

# Types d'événements (1 octet)
EVT_FEEDBACK = 0x01
EVT_PREDICTION = 0x02
EVT_PATCH = 0x03
EVT_CERTIFICATE = 0x04
EVT_REPAIR = 0x05
EVT_MODE_CHANGE = 0x06
EVT_REPORT = 0x07
EVT_ENGINEER_TICK = 0x08
EVT_SYSTEM = 0xFF

EVENT_NAMES = {
    EVT_FEEDBACK: "feedback",
    EVT_PREDICTION: "prediction",
    EVT_PATCH: "patch",
    EVT_CERTIFICATE: "certificate",
    EVT_REPAIR: "repair",
    EVT_MODE_CHANGE: "mode_change",
    EVT_REPORT: "report",
    EVT_ENGINEER_TICK: "engineer_tick",
    EVT_SYSTEM: "system",
}

DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
DEFAULT_BLACKBOX_DIR = "/var/db/pixelos/blackbox"


@dataclass
class BlackBoxRecord:
    event_type: int
    timestamp_us: int
    payload: dict
    _file_offset: int = -1

    @property
    def event_name(self) -> str:
        return EVENT_NAMES.get(self.event_type, f"unknown(0x{self.event_type:02x})")

    @property
    def timestamp(self) -> float:
        return self.timestamp_us / 1_000_000

    def to_dict(self) -> dict:
        return {
            "type": self.event_name,
            "type_code": self.event_type,
            "timestamp_us": self.timestamp_us,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def to_csv_row(self) -> list:
        return [
            self.event_name,
            str(self.timestamp_us),
            json.dumps(self.payload, ensure_ascii=False),
        ]


class PixBlackBox:
    """Enregistreur de vol binaire.

    Stockage sur disque au format .pxbb + index mémoire
    pour les requêtes sans relecture intégrale.
    """

    def __init__(self, directory: str = DEFAULT_BLACKBOX_DIR,
                 max_file_size: int = DEFAULT_MAX_FILE_SIZE,
                 max_memory_records: int = 50000):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_file_size = max_file_size
        self._max_memory_records = max_memory_records

        self._lock = threading.Lock()
        self._records: list[BlackBoxRecord] = []
        self._file: Optional[BinaryIO] = None
        self._file_path: Path = self._dir / "pixblackbox.pxbb"
        self._file_size = 0
        self._record_count = 0

        self._open_file()

    # ── Gestion fichier ───────────────────────────────────

    def _open_file(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = open(self._file_path, "a+b")
        self._file.seek(0, io.SEEK_END)
        self._file_size = self._file.tell()

        if self._file_size == 0:
            self._write_header()
        else:
            self._file.seek(0)
            magic = self._file.read(4)
            if magic != PXBB_MAGIC:
                self._file.close()
                backup = self._file_path.with_suffix(".pxbb.corrupted")
                self._file_path.rename(backup)
                self._file = open(self._file_path, "w+b")
                self._write_header()
            else:
                self._file.seek(0, io.SEEK_END)

    def _write_header(self):
        self._file.write(PXBB_MAGIC)
        self._file.write(struct.pack(">H", PXBB_VERSION))
        self._file.write(struct.pack(">H", 0))  # reserved
        self._file.flush()
        self._file_size = HEADER_SIZE

    def _maybe_rotate(self):
        if self._file_size >= self._max_file_size:
            self._file.close()
            backup = self._dir / f"pixblackbox_{int(time.time())}.pxbb"
            self._file_path.rename(backup)
            self._file = open(self._file_path, "wb")
            self._write_header()
            with self._lock:
                self._records.clear()

    def close(self):
        with self._lock:
            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

    # ── Enregistrement ─────────────────────────────────────

    def record(self, event_type: int, payload: dict,
               timestamp_us: Optional[int] = None) -> BlackBoxRecord:
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)

        rec = BlackBoxRecord(
            event_type=event_type,
            timestamp_us=timestamp_us,
            payload=payload,
        )

        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        data = struct.pack(f">BqI", event_type, timestamp_us, len(encoded)) + encoded

        with self._lock:
            self._records.append(rec)
            if len(self._records) > self._max_memory_records:
                self._records.pop(0)

            if self._file:
                self._file.write(data)
                self._file.flush()
                self._file_size += len(data)
                self._record_count += 1
                self._maybe_rotate()

        return rec

    # ── Enregistrements simplifiés ─────────────────────────

    def record_feedback(self, feedback) -> BlackBoxRecord:
        if hasattr(feedback, "to_dict"):
            payload = feedback.to_dict()
        else:
            payload = {"node_id": feedback.node_id, "status_code": feedback.status_code}
        return self.record(EVT_FEEDBACK, payload,
                          timestamp_us=getattr(feedback, "timestamp_us",
                                               int(time.time() * 1_000_000)))

    def record_prediction(self, pred) -> BlackBoxRecord:
        payload = pred.to_dict() if hasattr(pred, "to_dict") else {"node_id": pred.node_id}
        return self.record(EVT_PREDICTION, payload)

    def record_patch(self, patch_result) -> BlackBoxRecord:
        payload = patch_result.to_dict() if hasattr(patch_result, "to_dict") else {}
        return self.record(EVT_PATCH, payload)

    def record_certificate(self, cert) -> BlackBoxRecord:
        payload = cert.to_dict() if hasattr(cert, "to_dict") else {}
        return self.record(EVT_CERTIFICATE, payload)

    def record_repair(self, order) -> BlackBoxRecord:
        payload = order.to_dict() if hasattr(order, "to_dict") else {"node_id": order.node_id}
        return self.record(EVT_REPAIR, payload)

    def record_mode_change(self, mode: str) -> BlackBoxRecord:
        return self.record(EVT_MODE_CHANGE, {"mode": mode})

    def record_report(self, report) -> BlackBoxRecord:
        payload = report.to_dict() if hasattr(report, "to_dict") else {}
        return self.record(EVT_REPORT, payload)

    # ── Requêtes ───────────────────────────────────────────

    def query(self, event_type: Optional[int] = None,
              start_time_us: Optional[int] = None,
              end_time_us: Optional[int] = None,
              limit: Optional[int] = None,
              node_id: Optional[str] = None) -> list[BlackBoxRecord]:
        results = []

        with self._lock:
            records = list(self._records)

        for rec in records:
            if event_type is not None and rec.event_type != event_type:
                continue
            if start_time_us is not None and rec.timestamp_us < start_time_us:
                continue
            if end_time_us is not None and rec.timestamp_us > end_time_us:
                continue
            if node_id is not None:
                payload_node = rec.payload.get("node_id", "")
                if isinstance(payload_node, str) and node_id not in payload_node:
                    continue
            results.append(rec)
            if limit is not None and len(results) >= limit:
                break

        return results

    def count(self, event_type: Optional[int] = None) -> int:
        with self._lock:
            if event_type is None:
                return len(self._records)
            return sum(1 for r in self._records if r.event_type == event_type)

    # ── Export CSV ─────────────────────────────────────────

    def export_csv(self, path: str, **query_kwargs) -> str:
        records = self.query(**query_kwargs)
        path = str(path)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["event_type", "timestamp_us", "payload_json"])
            for rec in records:
                writer.writerow(rec.to_csv_row())

        return path

    def export_csv_string(self, **query_kwargs) -> str:
        records = self.query(**query_kwargs)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["event_type", "timestamp_us", "payload_json"])
        for rec in records:
            writer.writerow(rec.to_csv_row())
        return output.getvalue()

    # ── Rejeu ──────────────────────────────────────────────

    def replay(self) -> Iterator[BlackBoxRecord]:
        with self._lock:
            for rec in list(self._records):
                yield rec

    def replay_from_disk(self) -> Iterator[BlackBoxRecord]:
        if not self._file_path.exists():
            return

        with open(self._file_path, "rb") as f:
            magic = f.read(4)
            if magic != PXBB_MAGIC:
                return
            f.read(4)  # version + reserved

            while True:
                header = f.read(RECORD_OVERHEAD)
                if len(header) < RECORD_OVERHEAD:
                    break
                event_type, timestamp_us, payload_len = struct.unpack(
                    ">BqI", header
                )
                payload_data = f.read(payload_len)
                if len(payload_data) < payload_len:
                    break
                try:
                    payload = json.loads(payload_data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = {"_raw": payload_data.hex()}

                yield BlackBoxRecord(
                    event_type=event_type,
                    timestamp_us=timestamp_us,
                    payload=payload,
                )

    # ── Statistiques ───────────────────────────────────────

    def stats(self) -> dict:
        type_counts = {}
        with self._lock:
            for rec in self._records:
                name = rec.event_name
                type_counts[name] = type_counts.get(name, 0) + 1

        return {
            "total_records": self._record_count,
            "memory_records": len(self._records),
            "memory_max": self._max_memory_records,
            "file_size": self._file_size,
            "file_path": str(self._file_path),
            "max_file_size": self._max_file_size,
            "by_type": type_counts,
        }

    # ── Intégration PixEngineer ────────────────────────────

    def attach_to_engineer(self, engineer) -> list[str]:
        hooks = []
        hw = engineer._hardware
        pred = engineer._predict
        mb = engineer._maintenance_bot

        if hw:
            hw.on_stress = lambda fb: self.record_feedback(fb)
            hw.on_critical = lambda fb: self.record_feedback(fb)
            hw.on_failure = lambda fb: self.record_feedback(fb)
            hooks.append("hardware_callbacks")

        if pred:
            old_updated = pred.on_prediction_updated
            def on_pred(p, _old=old_updated):
                self.record_prediction(p)
                if _old:
                    _old(p)
            pred.on_prediction_updated = on_pred
            hooks.append("prediction_callback")

        if mb:
            old_started = mb.on_repair_started
            def on_rep_start(order, _old=old_started):
                self.record_repair(order)
                if _old:
                    _old(order)
            mb.on_repair_started = on_rep_start

            old_completed = mb.on_repair_completed
            def on_rep_comp(order, _old=old_completed):
                self.record_repair(order)
                if _old:
                    _old(order)
            mb.on_repair_completed = on_rep_comp

            old_cert = mb.on_cert_issued
            def on_cert(cert, _old=old_cert):
                self.record_certificate(cert)
                if _old:
                    _old(cert)
            mb.on_cert_issued = on_cert
            hooks.append("maintenance_callbacks")

        old_mode = engineer.on_mode_change
        def on_mode(mode, _old=old_mode):
            self.record_mode_change(mode)
            if _old:
                _old(mode)
        engineer.on_mode_change = on_mode

        old_report = engineer.on_report
        def on_report(report, _old=old_report):
            self.record_report(report)
            if _old:
                _old(report)
        engineer.on_report = on_report

        old_emergency = engineer.on_emergency
        def on_emergency(hw_status, _old=old_emergency):
            self.record(EVT_ENGINEER_TICK, {"event": "emergency", "hw_status": {
                "total": hw_status.get("total_nodes", 0),
                "failures": hw_status.get("failure", 0),
                "critical": hw_status.get("critical", 0),
            }})
            if _old:
                _old(hw_status)
        engineer.on_emergency = on_emergency

        hooks.extend(["mode_change", "report", "emergency"])
        self.record(EVT_SYSTEM, {"event": "attach", "hooks": hooks})
        return hooks


__all__ = [
    "PixBlackBox", "BlackBoxRecord",
    "EVT_FEEDBACK", "EVT_PREDICTION", "EVT_PATCH",
    "EVT_CERTIFICATE", "EVT_REPAIR", "EVT_MODE_CHANGE",
    "EVT_REPORT", "EVT_ENGINEER_TICK", "EVT_SYSTEM",
    "EVENT_NAMES",
]
