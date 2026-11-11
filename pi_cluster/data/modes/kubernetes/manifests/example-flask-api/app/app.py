import os
import socket

from flask import Flask

app = Flask(__name__)


@app.route("/")
def hello():
    node = os.environ.get("NODE_NAME", "unknown node")
    return f"Hello from pod {socket.gethostname()} on {node}!\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3003)
