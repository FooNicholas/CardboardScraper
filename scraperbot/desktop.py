"""One-click desktop launcher used by native JP Price Checker releases."""

from __future__ import annotations

from threading import Timer
import webbrowser

from scraperbot.web import build_web_application, create_server


def main() -> None:
    """Start a localhost server on an available port and open the browser UI."""
    application = build_web_application()
    server = create_server(application, host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}"

    # Opening slightly after the event loop begins prevents macOS from
    # foregrounding a blank browser tab while the server is still binding.
    Timer(0.2, lambda: webbrowser.open(url, new=1)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        application.catalogue.close()


if __name__ == "__main__":
    main()
