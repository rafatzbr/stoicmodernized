"""Image generation stage module using stable diffusion CLI."""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import ImageAsset


class ImageGenerationStage:
    """Handles image generation for scenes."""

    def __init__(self, job_id: str, mock: bool = False):
        """Initialize image generation stage.

        Args:
            job_id: Unique job identifier
            mock: If True, use mock data
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.images_dir = self.job_dir / "images"

        # SD-CLI configuration
        self.sd_cli_path = settings.sd_cli_path
        self.sd_model_path = settings.sd_model_path
        self.sd_clip_l_path = settings.sd_clip_l_path
        self.sd_clip_g_path = settings.sd_clip_g_path
        self.sd_t5xxl_path = settings.sd_t5xxl_path
        self.sd_width = settings.sd_image_width
        self.sd_height = settings.sd_image_height
        self.sd_cfg_scale = settings.sd_cfg_scale
        self.sd_sampling_method = settings.sd_sampling_method

    async def run(self, scene_plan: dict) -> list[ImageAsset]:
        """Generate images for all scenes.

        Args:
            scene_plan: Scene plan with visual prompts

        Returns:
            List of ImageAsset objects
        """
        self.images_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_generate(scene_plan)
        else:
            return await self._real_generate(scene_plan)

    async def _mock_generate(self, scene_plan: dict) -> list[ImageAsset]:
        """Mock image generation."""
        assets = []
        for scene in scene_plan.get("scenes", []):
            image_path = self.images_dir / f"scene_{scene['scene_number']:03d}.jpg"
            image_path.touch()  # Create empty file

            assets.append(
                ImageAsset(
                    scene_number=scene["scene_number"],
                    image_path=str(image_path),
                    prompt=scene["visual_prompt"],
                    seed=-1,  # Random seed
                )
            )

        return assets

    async def _real_generate(self, scene_plan: dict) -> list[ImageAsset]:
        """Generate real images using sd-cli.

        Returns:
            List of ImageAsset objects
        """
        assets = []

        # Default prompt components
        base_prompt = (
            "vertical composition, minimalist stoic background, ancient roman column "
            "silhouette, black marble texture, gold accents, dramatic cinematic lighting, "
            "dark philosophical aesthetic, empty center space"
        )

        negative_prompt = (
            "people, face, crowd, beach, ocean, water, snow, text, logo"
        )

        for scene in scene_plan.get("scenes", []):
            scene_num = scene["scene_number"]
            image_path = self.images_dir / f"scene_{scene_num:03d}.jpg"

            # Combine base prompt with scene-specific prompt
            full_prompt = f"{base_prompt}, {scene['visual_prompt']}"

            try:
                await self._generate_single_image(
                    prompt=full_prompt,
                    output_path=image_path,
                    negative_prompt=negative_prompt,
                )

                assets.append(
                    ImageAsset(
                        scene_number=scene_num,
                        image_path=str(image_path),
                        prompt=full_prompt,
                        seed=-1,
                    )
                )

            except Exception as e:
                print(f"Error generating image for scene {scene_num}: {e}")
                # Create placeholder
                image_path.touch()

                assets.append(
                    ImageAsset(
                        scene_number=scene_num,
                        image_path=str(image_path),
                        prompt=full_prompt,
                        seed=-1,
                    )
                )

        return assets

    async def _generate_single_image(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        seed: int = -1,
    ) -> None:
        """Generate a single image using sd-cli.

        Args:
            prompt: Image generation prompt
            output_path: Path to save image
            negative_prompt: Negative prompt
            seed: Random seed (-1 for random)
        """
        cmd = [
            self.sd_cli_path,
            "-m", self.sd_model_path,
            "--clip_l", self.sd_clip_l_path,
            "--clip_g", self.sd_clip_g_path,
            "--t5xxl", self.sd_t5xxl_path,
            "-H", str(self.sd_height),
            "-W", str(self.sd_width),
            "-p", prompt,
            "-n", negative_prompt,
            "--cfg-scale", str(self.sd_cfg_scale),
            "--sampling-method", self.sd_sampling_method,
            "-v",  # Verbose
            "--clip-on-cpu",
            "--vae-on-cpu",
            "--seed", str(seed),
        ]

        # Add output path
        cmd.extend(["-o", str(output_path)])

        # Run command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"sd-cli failed: {result.stderr}")

    def save_assets(self, assets: list[ImageAsset]) -> Path:
        """Save image assets to JSON.

        Args:
            assets: List of ImageAsset objects

        Returns:
            Path to saved JSON file
        """
        from src.utils import save_json

        data = {
            "images": [a.model_dump() for a in assets],
            "generated_at": "TODO: Add timestamp",
        }
        return save_json(data, self.images_dir / "assets.json")

    def load_assets(self) -> Optional[list[ImageAsset]]:
        """Load image assets from JSON.

        Returns:
            List of ImageAsset objects if found, None otherwise
        """
        from src.utils import load_json

        assets_path = self.images_dir / "assets.json"
        if not assets_path.exists():
            return None

        data = load_json(assets_path)
        return [ImageAsset(**a) for a in data.get("images", [])]
