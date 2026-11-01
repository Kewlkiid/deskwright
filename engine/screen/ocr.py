"""On-device text boxes (macOS Vision framework): every line of text on a screenshot with its box, in ~0.2-0.5s.

Used as extra grounding candidates next to SAM's: SAM finds icons and images well but returns nothing for plain
text (channel names, menu items, placeholders), which is most of what a script clicks in text-heavy apps.
Returns [] where the framework isn't available.
"""
from __future__ import annotations

import io
import sys

from PIL import Image

try:
    if sys.platform != "darwin":
        raise ImportError
    import Vision  # pyobjc-framework-Vision
    from Foundation import NSData
except ImportError:  # other platforms, or the binding isn't installed
    Vision = None


def available() -> bool:
    return Vision is not None


def text_boxes(img: Image.Image, accurate: bool = False) -> list[tuple[list[float], str]]:
    """[(box [x1, y1, x2, y2] in image pixels, text)] for each recognised line."""
    if Vision is None:
        return []
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate if accurate
                                 else Vision.VNRequestTextRecognitionLevelFast)
    request.setUsesLanguageCorrection_(False)
    ok, _err = handler.performRequests_error_([request], None)
    if not ok:
        return []
    w, h = img.size
    out = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        text = str(candidates[0].string()).strip()
        if not text:
            continue
        r = obs.boundingBox()  # normalised, origin at the bottom left
        x1, y1 = r.origin.x * w, (1 - r.origin.y - r.size.height) * h
        out.append(([x1, y1, x1 + r.size.width * w, y1 + r.size.height * h], text))
    return out
