import argparse
import webbrowser
from pathlib import Path
from . import render


def main():
    parser = argparse.ArgumentParser(description="Browse RipSat layouts in an offline HTML viewer.")
    parser.add_argument("catalogs", nargs="+", help="Bake directories or catalog JSON files")
    parser.add_argument("--program", help="Donor program.json for rule names and port types")
    parser.add_argument("-o", "--output", default="ripsat.html")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--egraph", action="store_true", help="Browse RipenInput e-classes and e-nodes")
    parser.add_argument("--port", type=int, default=0, help="Local e-graph viewer port")
    args = parser.parse_args()
    try:
        if args.egraph:
            from .egraph_view import serve
            return serve(args.catalogs, args.program, args.port, not args.no_open)
        page = render(args.catalogs, args.output, args.program).resolve()
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        parser.exit(1, f"ripsat-view: {exc}\n")
    print(page)
    if not args.no_open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
