"""Bounded multipart/raw request ingestion using a maintained streaming parser."""

from __future__ import annotations

from typing import BinaryIO

from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header

CHUNK_SIZE = 64 * 1024
MULTIPART_OVERHEAD = 64 * 1024


class InvalidUpload(ValueError):
    pass


class UploadTooLarge(InvalidUpload):
    pass


def receive_upload(
    source: BinaryIO, target: BinaryIO, content_type: str, length: int, max_file_size: int
) -> tuple[str | None, int]:
    mime, options = parse_options_header(content_type)
    received = 0
    filename = None
    if mime != b"multipart/form-data":
        if length > max_file_size:
            raise UploadTooLarge("File exceeds upload limit")
        remaining = length
        while remaining:
            data = source.read(min(remaining, CHUNK_SIZE))
            if not data:
                raise InvalidUpload("Incomplete request body")
            target.write(data)
            remaining -= len(data)
        return None, length

    boundary = options.get(b"boundary", b"")
    if not boundary or len(boundary) > 200:
        raise InvalidUpload("Missing or invalid multipart boundary")
    headers: dict[bytes, bytes] = {}
    field = bytearray()
    value = bytearray()
    header_size = 0
    parts = 0
    finished = False

    def part_begin() -> None:
        nonlocal parts
        parts += 1
        if parts != 1:
            raise InvalidUpload("Upload exactly one file per request")

    def header_field(data: bytes, start: int, end: int) -> None:
        nonlocal header_size
        header_size += end - start
        if header_size > 8192:
            raise InvalidUpload("Multipart headers too large")
        field.extend(data[start:end])

    def header_value(data: bytes, start: int, end: int) -> None:
        nonlocal header_size
        header_size += end - start
        if header_size > 8192:
            raise InvalidUpload("Multipart headers too large")
        value.extend(data[start:end])

    def header_end() -> None:
        key = bytes(field).lower()
        if key in headers:
            raise InvalidUpload("Duplicate multipart header")
        headers[key] = bytes(value)
        field.clear()
        value.clear()

    def headers_finished() -> None:
        nonlocal filename
        disposition, params = parse_options_header(headers.get(b"content-disposition", b""))
        if (
            disposition != b"form-data"
            or params.get(b"name") != b"file"
            or b"filename" not in params
        ):
            raise InvalidUpload("Expected a multipart file field named file")
        filename = params[b"filename"].decode("utf-8", errors="replace")

    def part_data(data: bytes, start: int, end: int) -> None:
        nonlocal received
        received += end - start
        if received > max_file_size:
            raise UploadTooLarge("File exceeds upload limit")
        target.write(data[start:end])

    def on_end() -> None:
        nonlocal finished
        finished = True

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": part_begin,
            "on_header_field": header_field,
            "on_header_value": header_value,
            "on_header_end": header_end,
            "on_headers_finished": headers_finished,
            "on_part_data": part_data,
            "on_end": on_end,
        },
    )
    remaining = length
    while remaining:
        data = source.read(min(remaining, CHUNK_SIZE))
        if not data:
            raise InvalidUpload("Incomplete request body")
        parser.write(data)
        remaining -= len(data)
    parser.finalize()
    if not finished or parts != 1 or filename is None:
        raise InvalidUpload("Incomplete multipart file")
    return filename, received
