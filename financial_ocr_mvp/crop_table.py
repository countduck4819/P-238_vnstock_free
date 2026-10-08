from PIL import Image


img = Image.open(
    "images/page_005_rotated.png"
)


table = img.crop(
    (
        120,
        330,
        2200,
        1250
    )
)


table.save(
    "images/page_005_table.png"
)


print("saved")