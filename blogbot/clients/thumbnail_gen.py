from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

from blogbot.utils import safe_ascii_filename

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

GRADIENTS = [
    ((41, 128, 185), (44, 62, 80)),
    ((142, 68, 173), (44, 62, 80)),
    ((39, 174, 96), (22, 160, 133)),
    ((231, 76, 60), (192, 57, 43)),
    ((243, 156, 18), (211, 84, 0)),
    ((52, 152, 219), (142, 68, 173)),
    ((26, 188, 156), (41, 128, 185)),
    ((230, 126, 34), (231, 76, 60)),
]

WIDTH = 1200
HEIGHT = 630


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_gradient(draw: ImageDraw.ImageDraw, color_a: tuple, color_b: tuple) -> None:
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(color_a[0] + (color_b[0] - color_a[0]) * ratio)
        g = int(color_a[1] + (color_b[1] - color_a[1]) * ratio)
        b = int(color_a[2] + (color_b[2] - color_a[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _wrap_title(title: str, max_chars: int = 16) -> list[str]:
    if len(title) <= max_chars:
        return [title]
    lines: list[str] = []
    for raw_line in textwrap.wrap(title, width=max_chars):
        lines.append(raw_line)
    return lines or [title]


def generate_title_thumbnail(title: str, index: int = 0) -> Image.Image:
    """주제 제목으로 그라데이션 썸네일 이미지를 생성한다."""
    palette_idx = (abs(hash(title)) + index) % len(GRADIENTS)
    color_a, color_b = GRADIENTS[palette_idx]

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, color_a, color_b)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    circle_r = 200
    cx, cy = WIDTH - 150, HEIGHT - 120
    ov_draw.ellipse(
        [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
        fill=(255, 255, 255, 25),
    )
    cx2, cy2 = 120, 80
    ov_draw.ellipse(
        [cx2 - 120, cy2 - 120, cx2 + 120, cy2 + 120],
        fill=(255, 255, 255, 15),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    lines = _wrap_title(title, max_chars=14)
    font_size = 72 if len(lines) <= 2 else 56
    font = _find_font(font_size)

    line_height = font_size + 16
    total_text_height = line_height * len(lines)
    start_y = (HEIGHT - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) // 2
        y = start_y + i * line_height

        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 80))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    sub_font = _find_font(24)
    sub_text = "logofknowledge.com"
    sb = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = sb[2] - sb[0]
    draw.text(
        ((WIDTH - sw) // 2, HEIGHT - 60),
        sub_text,
        font=sub_font,
        fill=(255, 255, 255, 180),
    )

    return img


def save_title_thumbnail(title: str, index: int = 1) -> Path:
    """썸네일을 생성하고 로컬에 저장한 뒤 경로를 반환한다."""
    img = generate_title_thumbnail(title, index=index)
    out_dir = Path("downloads")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_ascii_filename(title)}-thumb-{index}.png"
    img.save(out_path, "PNG")
    return out_path
