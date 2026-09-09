"""
VisionAnalyzer — Step 5.2 + 5.5 connector
=============================================
Hinglish: Ye class Capture aur VisionProvider ko jodta hai — poora
"capture -> analyze" pipeline. Agent/Tool sirf isse baat karega,
andar kaunsa capture strategy hai ya kaunsa vision provider, isse
farak nahi padta.
"""


class VisionAnalyzer:

    def __init__(self, capture, vision_provider):
        # Dependency Injection — jaisa hamesha karte hain
        self._capture = capture
        self._vision_provider = vision_provider

    def observe(self, filepath: str, context: dict = None):
        """
        Hinglish: Image capture karta hai, phir vision provider ko
        bhejta hai analysis ke liye. Return: VisualObservation
        """
        image_path = self._capture.capture(filepath)
        return self._vision_provider.analyze(image_path, context or {})