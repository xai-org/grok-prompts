"""Values taken from the xAI image docs as of 15 November 2026.

Generation: https://docs.x.ai/developers/model-capabilities/images/generation
Editing: https://docs.x.ai/developers/model-capabilities/images/editing
Multi-image: https://docs.x.ai/developers/model-capabilities/images/multi-image-editing
REST reference: https://docs.x.ai/developers/rest-api-reference/inference/images
"""

__version__ = "0.1.0"
DEFAULT_MODEL = "grok-imagine-image-2.0"
API_BASE = "https://api.x.ai/v1"
GENERATIONS_PATH = "/images/generations"
EDITS_PATH = "/images/edits"

# REST ImageAspectRatio. Includes ratios the Python SDK enum map did not
# expose on current main (21:9, 5:2, auto).
ASPECT_RATIOS = (
    "1:1",
    "3:4",
    "4:3",
    "9:16",
    "16:9",
    "2:3",
    "3:2",
    "9:19.5",
    "19.5:9",
    "9:20",
    "20:9",
    "1:2",
    "2:1",
    "21:9",
    "5:2",
    "auto",
)

# REST ImageResolution.
RESOLUTIONS = ("1k", "2k", "1.5k")

# Prompting guide: low, medium, and auto. Auto serves low on generation
# and medium on edit. The Python SDK accepts only low and medium.
QUALITIES = ("low", "medium", "auto")

MAX_IMAGES = 10
MAX_REFERENCE_IMAGES = 5
DEFAULT_TIMEOUT_SECONDS = 180.0
USER_AGENT = "grok-imagine/0.1"

# The edit API addresses entries of the `images` array with these tokens.
IMAGE_TOKEN_PREFIX = "<IMAGE_"
