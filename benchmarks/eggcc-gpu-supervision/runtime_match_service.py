"""Persistent Metal exact candidate filter for the Rust Cell CPU executor."""
import json
import socket
import sys
import time

import mlx.core as mx


def select(request):
    rows = mx.array(request["rows"], dtype=mx.int32)
    bound = mx.array(request["bound"], dtype=mx.int32)
    live = mx.array(request["live"], dtype=mx.bool_)
    mask = live & mx.all((bound[None, :] < 0) | (rows == bound[None, :]), axis=1)
    for left, right in request["equal"]:
        mask = mask & (rows[:, left] == rows[:, right])
    mx.eval(mask)
    return mask.tolist()


def main():
    mx.set_default_device(mx.gpu)
    with socket.create_connection(("127.0.0.1", int(sys.argv[1]))) as connection:
        with connection.makefile("rwb") as stream:
            for line in stream:
                request = json.loads(line)
                start = time.perf_counter()
                mask = select(request)
                result = dict(mask=mask, complete=True, seconds=time.perf_counter() - start)
                stream.write(json.dumps(result).encode() + b"\n")
                stream.flush()


if __name__ == "__main__":
    main()
