"""Иконка приложения: страница, одна строка распознана OCR.

Каждый размер рисуется отдельно со сверхсэмплингом x4 — при уменьшении
из одного мастера 1024px тонкие строки на 16 и 32 px схлопываются.
Пропорции по сетке macOS: тело иконки 824/1024 от холста.

    python desktop/make_icon.py
    iconutil -c icns desktop/icons/AppIcon.iconset -o desktop/icons/AppIcon.icns
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "icons" / "AppIcon.iconset"
SUPERSAMPLE = 4

# Корпус тёмный ради силуэта: светлая заливка растворялась на белых обоях
# уже на 32 px. Синий остаётся единственным цветным элементом иконки —
# то же правило, что и в интерфейсе: синий значит «страница прошла OCR».
BODY = "#39424f"
PAGE = "#ffffff"
LINE = "#b3bcc9"
OCR = "#0060df"

# доли от стороны холста
BODY_INSET, BODY_RADIUS = 100 / 1024, 185 / 1024
PAGE_X, PAGE_W = 288 / 1024, 448 / 1024
PAGE_Y, PAGE_H = 225 / 1024, 574 / 1024
PAGE_R = 45 / 1024
LINE_X, LINE_W, LINE_H = 360 / 1024, 305 / 1024, 45 / 1024
LINE_Y = [333 / 1024, 431 / 1024, 530 / 1024, 628 / 1024]
OCR_INDEX_4, OCR_INDEX_3 = 2, 1

SIZES = {
    16: ["icon_16x16.png"],
    32: ["icon_16x16@2x.png", "icon_32x32.png"],
    64: ["icon_32x32@2x.png"],
    128: ["icon_128x128.png"],
    256: ["icon_128x128@2x.png", "icon_256x256.png"],
    512: ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}


def draw_icon(size: int) -> Image.Image:
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def px(fraction: float) -> float:
        return fraction * canvas

    inset = px(BODY_INSET)
    draw.rounded_rectangle(
        [inset, inset, canvas - inset, canvas - inset],
        radius=px(BODY_RADIUS),
        fill=BODY,
    )
    draw.rounded_rectangle(
        [px(PAGE_X), px(PAGE_Y), px(PAGE_X + PAGE_W), px(PAGE_Y + PAGE_H)],
        radius=px(PAGE_R),
        fill=PAGE,
    )

    # на мелких размерах четыре строки сливаются — оставляем три
    rows = LINE_Y if size >= 128 else [LINE_Y[0], LINE_Y[1], LINE_Y[3]]
    ocr_index = OCR_INDEX_4 if size >= 128 else OCR_INDEX_3
    height = max(px(LINE_H), SUPERSAMPLE)

    for index, top in enumerate(rows):
        y = px(top)
        draw.rounded_rectangle(
            [px(LINE_X), y, px(LINE_X + LINE_W), y + height],
            radius=height / 2,
            fill=OCR if index == ocr_index else LINE,
        )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size, names in SIZES.items():
        icon = draw_icon(size)
        for name in names:
            icon.save(OUT / name)
    print(f"{sum(len(n) for n in SIZES.values())} файлов в {OUT}")


if __name__ == "__main__":
    main()
