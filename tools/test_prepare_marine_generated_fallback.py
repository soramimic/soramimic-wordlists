import tempfile
import unittest
import sys
from unittest import mock
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_marine_generated_fallback as generated


class MarineGeneratedFallbackTest(unittest.TestCase):
    def test_prepares_fixed_size_webp_with_badge_region(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "output.webp"
            Image.new("RGB", (1200, 800), "#2878a0").save(source)
            # CIに日本語フォントを追加せず、レイアウト処理だけ同梱フォントで検査する。
            with mock.patch.object(
                generated, "FONT_CANDIDATES",
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",),
            ):
                generated.prepare(source, output)
            with Image.open(output) as image:
                self.assertEqual(generated.SIZE, image.size)
                self.assertEqual("WEBP", image.format)
                # 右上の暗色バッジで、一様な入力から画素が変化している。
                self.assertNotEqual(image.getpixel((900, 35)), image.getpixel((100, 100)))
        self.assertEqual("生成イメージ", generated.LABEL)


if __name__ == "__main__":
    unittest.main()
