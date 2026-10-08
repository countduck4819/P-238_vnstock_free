from PIL import Image


img = Image.open(
    "images/page_005.png"
)


# xoay 90 độ
rotated = img.rotate(
    -90,
    expand=True
)


rotated.save(
    "images/page_005_rotated.png"
)


print("done")