# -*- coding: utf-8 -*-
"""Run the Broost website and admin dashboard locally."""

import uvicorn
from webapp.server import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=False)
