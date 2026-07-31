from modules.visuals.ai_image import AIImageGenerator
from modules.visuals.scene import SceneImageService
from channels.minute_mystere.image_profile import MINUTE_MYSTERE_IMAGE_PROFILE


def create_image_generator() -> AIImageGenerator:
    return AIImageGenerator(
        image_profile=MINUTE_MYSTERE_IMAGE_PROFILE
    )


def create_scene_image_service() -> SceneImageService:
    image_generator = create_image_generator()
    return SceneImageService(generator=image_generator)