"""VisionAnalyzer"""


class VisionAnalyzer:

    def __init__(self, capture, vision_provider):
        self._capture = capture
        self._vision_provider = vision_provider

    def observe(self, filepath: str, context: dict = None):
        image_path = self._capture.capture(filepath)
        return self._vision_provider.analyze(image_path, context or {})