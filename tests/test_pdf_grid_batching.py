import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import pymupdf

from utils.pdf_utils import pdf_to_grid_images


class PdfGridBatchingTest(unittest.TestCase):
    def test_renders_at_most_four_pages_before_saving_each_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory, "pages.pdf")
            with pymupdf.open() as doc:
                for index in range(9):
                    page = doc.new_page(width=40, height=30)
                    page.draw_rect(page.rect, fill=(index / 10, 0, 0))
                doc.save(pdf_path)

            renders = []
            saves = []
            get_pixmap = pymupdf.Page.get_pixmap
            imwrite = cv2.imwrite

            def render(page, *args, **kwargs):
                renders.append(page.number)
                return get_pixmap(page, *args, **kwargs)

            def save(path, image):
                saves.append(len(renders))
                return imwrite(path, image)

            with (
                patch.object(pymupdf.Page, "get_pixmap", render),
                patch.object(cv2, "imwrite", save),
            ):
                image_paths = pdf_to_grid_images(pdf_path, directory, scale=1.0)

            self.assertEqual(renders, list(range(9)))
            self.assertEqual(saves, [4, 8, 9])
            self.assertEqual(
                [Path(path).name for path in image_paths],
                ["grid_1.png", "grid_2.png", "grid_3.png"],
            )
            last_grid = cv2.imread(image_paths[-1])
            self.assertEqual(last_grid.shape, (60, 80, 3))
            self.assertLess(last_grid[15, 20][2], 255)
            self.assertTrue((last_grid[15, 60] == 255).all())
            self.assertTrue((last_grid[45, 20] == 255).all())
            self.assertTrue((last_grid[45, 60] == 255).all())


if __name__ == "__main__":
    unittest.main()
