"""AvatarLive M0 self-test: verify flashhead module chain imports cleanly."""
import sys

sys.path.insert(0, "src")

from handlers.avatar.flashhead.flashhead_config import FlashHeadConfig
from handlers.avatar.flashhead.flashhead_face_crop import crop_face, crop_face_with_box
from handlers.avatar.flashhead.flashhead_processor import FlashHeadProcessor, FlashHeadProcessorCallbacks
from handlers.avatar.flashhead.avatar_handler_flashhead import HandlerAvatarFlashHead

c = FlashHeadConfig(cond_image_path="/tmp/x.jpg")
print("✅ flashhead 4 modules import OK")
print("   default ckpt:", c.ckpt_dir, "| model:", c.model_type)
print("   use_face_crop:", c.use_face_crop, "| idle_noise:", c.idle_noise_amplitude)

# sanity: paste_back-related functions/attrs present (pod-tested additions)
assert hasattr(crop_face_with_box, "__call__") or callable(crop_face_with_box)
from handlers.avatar.flashhead.flashhead_processor import FrameQueueItem  # noqa
print("✅ paste_back crop_face_with_box + FrameQueueItem present")
