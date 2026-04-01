from PIL import Image, ImageDraw

ICON_SIZE = 64

# Green (filtering on) and red (filtering off)
_COLOR_ON = (34, 197, 94, 255)
_COLOR_OFF = (239, 68, 68, 255)
_COLOR_RING = (255, 255, 255, 200)


def make_icon(enabled: bool) -> Image.Image:
    """
    Return a 64×64 RGBA PIL Image.
    Green filled circle = filtering enabled.
    Red filled circle   = filtering disabled.
    White ring for visibility on both light and dark taskbars.
    """
    img = Image.new('RGBA', (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = _COLOR_ON if enabled else _COLOR_OFF

    # Outer white ring
    draw.ellipse([2, 2, ICON_SIZE - 2, ICON_SIZE - 2], fill=_COLOR_RING)
    # Inner colored circle
    draw.ellipse([6, 6, ICON_SIZE - 6, ICON_SIZE - 6], fill=color)

    return img
