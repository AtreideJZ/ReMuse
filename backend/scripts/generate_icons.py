"""一次性生成 PWA 图标（构建期工具，不进运行时依赖）。

设计：主题色圆角方块底 + 白色「溯」字。
- icon-192/512：普通图标（带圆角与透明边）
- icon-maskable-192/512：maskable（全出血底，字符控制在 80% 安全区内）
- apple-touch-icon：180×180（iOS 主屏，全出血）

用法（在 backend/ 下）：
    .venv/Scripts/python scripts/generate_icons.py
输出到 frontend/public/icons/
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "icons"
BG = "#4f46e5"  # 主题 primary
FG = "#ffffff"
CHAR = "溯"
FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",      # Windows 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",    # Windows 黑体
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux 备用
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("找不到可用中文字体，请安装 Noto Sans CJK 或微软雅黑")


def draw_char(size: int, *, rounded: bool, char_ratio: float, filename: str) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=BG)
    else:
        d.rectangle([0, 0, size, size], fill=BG)
    font = load_font(int(size * char_ratio))
    bbox = d.textbbox((0, 0), CHAR, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    d.text((x, y), CHAR, font=font, fill=FG)
    img.save(OUT / filename)
    print(f"written: {filename} ({size}x{size})")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_char(192, rounded=True, char_ratio=0.55, filename="icon-192.png")
    draw_char(512, rounded=True, char_ratio=0.55, filename="icon-512.png")
    draw_char(192, rounded=False, char_ratio=0.42, filename="icon-maskable-192.png")
    draw_char(512, rounded=False, char_ratio=0.42, filename="icon-maskable-512.png")
    draw_char(180, rounded=False, char_ratio=0.55, filename="apple-touch-icon.png")


if __name__ == "__main__":
    main()
