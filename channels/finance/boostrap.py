from modules.visuals.ai_image import AIImageGenerator
from modules.visuals.scene import SceneImageService
from channels.finance.image_profile import FINANCE_IMAGE_PROFILE


def create_image_generator() -> AIImageGenerator:
    return AIImageGenerator(
        image_profile=FINANCE_IMAGE_PROFILE
    )


def create_scene_image_service() -> SceneImageService:
    image_generator = create_image_generator()
    return SceneImageService(generator=image_generator)