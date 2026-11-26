import argparse
import webbrowser
from pathlib import Path
from . import render


def main(stream_mode=False):
    parser = argparse.ArgumentParser(description="Browse RipSat layouts in an offline HTML viewer.")
    parser.add_argument("catalogs", nargs="*", help="Bake directories or catalog JSON files")
    parser.add_argument("--stream", help="Credit-scaling buffer shard (JSON or gzip)")
    parser.add_argument("--program", help="Donor program.json for rule names and port types")
    parser.add_argument("-o", "--output", default="ts_viz.html" if stream_mode else "ripsat.html")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--egraph", action="store_true", help="Browse RipenInput e-classes and e-nodes")
    parser.add_argument("--port", type=int, default=0, help="Local e-graph viewer port")
    args = parser.parse_args()
    if args.egraph and (stream_mode or not args.catalogs):
        parser.error("--egraph requires a catalog and its own local viewer mode")
    if stream_mode and not args.stream and args.catalogs:
        args.stream, *args.catalogs = args.catalogs
    try:
        if args.egraph:
            from .egraph_view import serve
            return serve(args.catalogs, args.program, args.port, not args.no_open, stream=args.stream)
        page = render(args.catalogs, args.output, args.program, stream=args.stream, start_stream=stream_mode).resolve()
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        parser.exit(1, f"ripsat-view: {exc}\n")
    print(page)
    if not args.no_open:
        webbrowser.open(page.as_uri())


def ts_viz():
    main(stream_mode=True)


if __name__ == "__main__":
    main()
