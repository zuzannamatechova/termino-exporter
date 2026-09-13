import json
import struct

import pytest

from termino_exporter.identity_protocol import (
    IdentityProtocolError,
    IncrementalFrameReader,
    clipped_timeout_ns,
    decode_frame,
    encode_frame,
    worker_exit_code,
)


def test_frame_round_trip_and_bytewise_partial_reads() -> None:
    frame = encode_frame("CLEAR", 17, {})
    reader = IncrementalFrameReader()
    for byte in frame:
        reader.feed(bytes([byte]))
    assert reader.complete
    assert decode_frame(reader.frame(), expected_type="CLEAR", expected_sequence_id=17) == {}


@pytest.mark.parametrize("partial", [b"\0", b"\0\0\0", struct.pack(">I", 5) + b"{}"])
def test_partial_prefix_or_body_is_deterministically_broken(partial: bytes) -> None:
    reader = IncrementalFrameReader()
    reader.feed(partial)
    with pytest.raises(IdentityProtocolError, match="^ID0_IPC_CHANNEL_BROKEN$"):
        reader.frame()


@pytest.mark.parametrize("size", [0, 32_769])
def test_zero_and_oversized_prefix_are_rejected(size: int) -> None:
    reader = IncrementalFrameReader()
    with pytest.raises(IdentityProtocolError, match="^ID0_INVALID_SANITIZED_PAYLOAD$"):
        reader.feed(struct.pack(">I", size))


def test_duplicate_json_key_wrong_version_type_and_sequence_are_rejected() -> None:
    bodies = [
        b'{"protocol_version":1,"protocol_version":1,"message_type":"CLEAR",'
        b'"sequence_id":1,"payload":{}}',
        json.dumps(
            {
                "protocol_version": 2,
                "message_type": "CLEAR",
                "sequence_id": 1,
                "payload": {},
            }
        ).encode(),
    ]
    for body in bodies:
        frame = struct.pack(">I", len(body)) + body
        with pytest.raises(IdentityProtocolError, match="^ID0_INVALID_SANITIZED_PAYLOAD$"):
            decode_frame(frame, expected_type="CLEAR", expected_sequence_id=1)
    frame = encode_frame("CLEAR", 1, {})
    with pytest.raises(IdentityProtocolError):
        decode_frame(frame, expected_type="SHUTDOWN", expected_sequence_id=1)
    with pytest.raises(IdentityProtocolError):
        decode_frame(frame, expected_type="CLEAR", expected_sequence_id=2)


def test_worker_exit_priority_prefers_partial_frame_then_reserved_status() -> None:
    assert worker_exit_code(started=True, bytes_received=1, status=71) == "ID0_IPC_CHANNEL_BROKEN"
    assert worker_exit_code(started=True, bytes_received=0, status=71) == "ID0_IPC_WRITE_TIMEOUT"
    assert (
        worker_exit_code(started=False, bytes_received=0, status=70)
        == "ID0_WORKER_BOOTSTRAP_FAILED"
    )


def test_timeout_is_clipped_without_restarting_global_budget() -> None:
    assert clipped_timeout_ns(5, 100, None) == 5_000_000_000
    assert clipped_timeout_ns(5, 100, 1_000) == 900
    assert clipped_timeout_ns(5, 1_000, 900) == 0
